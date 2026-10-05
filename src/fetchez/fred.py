#!/usr/bin/env python

"""
fetchez.fred
~~~~~~~~~~~~~

Fetches Remote Elevation Datalist (FRED)

Handles the indexing, storage, and spatial querying of remote datasets
that lack a public API but provide file lists (e.g., NCEI Thredds, USACE).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import logging
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from . import config, spatial, utils

logger = logging.getLogger(__name__)

# Directory where FRED index files are stored
THIS_DIR = Path(__file__).resolve().parent
FETCH_DATA_DIR = Path(THIS_DIR / "data")


class FRED:
    """FRED (Fetches Remote Elevation Datalist) manages a local GeoJSON-based index
    of remote files. It allows spatial queries to determine which files to download.
    """

    # Standard metadata schema
    SCHEMA = [
        "Name",
        "ID",
        "Date",
        "Agency",
        "MetadataLink",
        "MetadataDate",
        "DataLink",
        "IndexLink",
        "Link",
        "DataType",
        "DataSource",
        "Resolution",
        "HorizontalDatum",
        "VerticalDatum",
        "LastUpdate",
        "Etcetra",
        "Info",
    ]

    def __init__(self, name: str = "FRED", local: bool = False):
        self.name = name
        self.filename = f"{name}.geojson"

        # Default to local directory if not found in data dir
        if local:
            self.path = Path(self.filename)
        elif Path(FETCH_DATA_DIR / self.filename).exists():
            self.path = Path(FETCH_DATA_DIR / self.filename)
        elif Path(config.CONFIG_PATH / "indices" / self.filename).exists():
            self.path = Path(config.CONFIG_PATH / "indices" / self.filename)
        else:
            self.path = Path(self.filename)

        self.features: list[Any] = []
        self._load()

    def _load(self):
        """Load the GeoJSON file into memory."""

        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.features = data.get("features", [])

                msg = (
                    f"Loaded index {utils.colorize(self.name, utils.CYAN)} "
                    f"from {utils.str_truncate_middle(self.path)} "
                    f"({utils.colorize(str(len(self.features)), utils.BOLD)} items)"
                )
                logger.debug(msg)

            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Corrupt or unreadable index at {self.path}: {e}")
                self.features = []
        else:
            logger.debug(f"Index not found at {self.path}, starting empty.")
            logger.info(
                f"Initializing new index for {utils.colorize(self.name, utils.CYAN)}"
            )
            self.features = []

    def save(self):
        """Save the current features to the GeoJSON file."""

        data = {
            "type": "FeatureCollection",
            "name": self.name,
            "features": self.features,
        }

        # Ensure directory exists
        out_dir = self.path.parent
        if out_dir and not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))  # Compact JSON
            logger.info(f"Saved {len(self.features)} items to {self.name} index.")
        except OSError as e:
            logger.error(f"Failed to save FRED index {self.path}: {e}")

    def add_survey(self, geom: dict, **kwargs):
        """Add a single survey entry to the FRED database.

        Args:
            geom (Dict): GeoJSON geometry dictionary (e.g., {'type': 'Polygon', 'coordinates': ...})
            **kwargs: Attributes matching the schema.
        """

        props = kwargs.copy()
        props["LastUpdate"] = utils.this_date()

        # for field in self.SCHEMA:
        #     if field not in props:
        #         props[field] = None

        feature = {"type": "Feature", "properties": props, "geometry": geom}
        self.features.append(feature)

    def search(
        self,
        region: tuple[float, float, float, float] | None = None,
        where: list[str] | None = None,
        layer: str | None = None,
    ) -> list[dict]:
        """Search for data in the reference vector file.

        Args:
            region: Tuple (xmin, xmax, ymin, ymax) from spatial.parse_region
            where: List of simple SQL-style filters (e.g. "Agency = 'NOAA'")
                   (Currently supports simple equality checks for simplicity without SQL parser)
            layer: Filter by 'DataSource' field (e.g., 'ncei_thredds')

        Returns:
            List of dictionaries containing the properties of matching features.
        """

        where = where or []
        results = []

        search_geom = None
        if region is not None and spatial.region_valid_p(region):
            search_geom = spatial.region_to_shapely(region)

        if region:
            r_str = ",".join(f"{x:.2f}" for x in region)
            logger.debug(f"Searching {self.name} in region [{r_str}]...")

        for feat in self.features:
            props = feat.get("properties", {})
            geom = feat.get("geometry")

            if layer and props.get("DataSource") != layer:
                continue

            # Filter by Attributes ("where")
            match = True
            for clause in where:
                if "=" in clause:
                    k, v = [x.strip().strip("'").strip('"') for x in clause.split("=")]

                    val = props.get(k)
                    if str(val) != v:
                        match = False
                        break
            if not match:
                continue

            if search_geom and geom:
                try:
                    feat_shape = shape(geom)
                    if not search_geom.intersects(feat_shape):
                        continue
                except Exception:
                    continue

            results.append(props)

        logger.debug(f"FRED Search found {len(results)} items.")
        return results

    def _get_unique_values(self, field: str) -> list[Any]:
        """Helper to see unique values for a field (e.g. Agency)."""

        values = set()
        for f in self.features:
            val = f.get("properties", {}).get(field)
            if val:
                values.add(val)
        return list(values)

    def _detect_spatial_fields(
        self, row: dict
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Attempt to find W/E/S/N in a dictionary using common abbreviations."""

        keys_w = ["w", "west", "xmin", "min_lon", "min_x", "left"]
        keys_e = ["e", "east", "xmax", "max_lon", "max_x", "right"]
        keys_s = ["s", "south", "ymin", "min_lat", "min_y", "bottom"]
        keys_n = ["n", "north", "ymax", "max_lat", "max_y", "top"]

        def get_val(keys):
            for k in keys:
                # Try exact match
                if k in row:
                    return float(row[k])
                # Try Case-Insensitive
                for rk in row:
                    if rk.lower() == k:
                        return float(row[rk])
            return None

        return get_val(keys_w), get_val(keys_e), get_val(keys_s), get_val(keys_n)

    def ingest(
        self,
        source_file: str,
        field_map: dict[str, str] | None = None,
        wipe: bool = False,
    ):
        """Ingest a file listing (CSV or JSON) into the FRED index.

        Args:
            source_file: Path to the CSV or JSON file.
            field_map: Dictionary mapping Input_Header -> FRED_Field.
                       Example: {'file_url': 'DataLink', 'file_name': 'Name'}
            wipe: If True, clears existing index before ingesting.
        """

        import csv

        if not Path(source_file).exists():
            logger.error(f"Source file not found: {source_file}")
            return

        if wipe:
            self.features = []

        field_map = field_map or {}
        ext = source_file.split(".")[-1].lower()

        items = []

        try:
            if ext == "csv":
                with open(source_file, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    items = list(reader)
            elif ext == "json":
                with open(source_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        items = data
                    elif "files" in data:
                        items = data["files"]
                    elif "items" in data:
                        items = data["items"]
            else:
                logger.error("Unsupported file format. Use CSV or JSON.")
                return
        except Exception as exception:
            logger.error(f"Failed to read source file: {exception}")
            return

        logger.info(f"Ingesting {len(items)} items from {source_file}...")

        added = 0
        for item in items:
            props = {}

            for field in self.SCHEMA:
                if field in item:
                    props[field] = item[field]
                elif field.lower() in item:
                    props[field] = item[field.lower()]

            for src_k, dst_k in field_map.items():
                if src_k in item:
                    props[dst_k] = item[src_k]

            if "DataLink" not in props:
                for k, v in item.items():
                    if "url" in k.lower() or "link" in k.lower() or "path" in k.lower():
                        props["DataLink"] = v
                        break

            if "DataLink" not in props:
                logger.warning(f"Skipping item {item}: No DataLink/URL found.")
                continue

            link = props.get("DataLink")
            if link and not link.startswith("http") and not link.startswith("ftp"):
                abs_path = Path(link).resolve()
                props["DataLink"] = f"file://{abs_path}"

            w, e, s, n = self._detect_spatial_fields(item)

            if None in [w, e, s, n]:
                logger.warning(
                    f"Skipping item {props.get('Name')}: Missing spatial bounds."
                )
                continue

            # Create GeoJSON Polygon
            # Counter-clockwise: SW -> SE -> NE -> NW -> SW
            geom = {
                "type": "Polygon",
                "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
            }

            self.add_survey(geom, **props)
            added += 1

        logger.info(f"Successfully added {added} surveys to {self.name}.")
        self.save()
