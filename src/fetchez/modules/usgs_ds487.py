#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_ds487
~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Data Series 487 (High-Resolution Coastal Bathymetry) module using FRED.

FRED geometries are built from the authoritative ``DEMCoverageAreas`` polygon
shapefile.  Provenance is summarized from ``DataCoverageAreas``, which describes
the native datasets used to construct the 45 published 3 m DEMs.
"""

from __future__ import annotations

import json
import logging
import math
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from fetchez import core
from fetchez import fred
from fetchez.modules.base import FetchModule
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

DS487_BASE_URL = "https://pubs.usgs.gov/ds/487/"
DS487_DATA_URL = f"{DS487_BASE_URL}data/"
DS487_DEMS_URL = f"{DS487_DATA_URL}DEMs/"

DS487_DEM_COVERAGE_DIR_URL = f"{DS487_DATA_URL}DEMCoverageAreas/"
DS487_DEM_COVERAGE_URL = f"{DS487_DEM_COVERAGE_DIR_URL}DEMCoverageAreas.zip"

DS487_DATA_COVERAGE_DIR_URL = f"{DS487_DATA_URL}DataCoverageAreas/"
DS487_DATA_COVERAGE_URL = f"{DS487_DATA_COVERAGE_DIR_URL}DataCoverageAreas.zip"

DS487_METADATA_URL = f"{DS487_BASE_URL}metadata/DEM_fullmetadata.xml"
DS487_METADATA_XLS_URL = f"{DS487_DATA_URL}DEM_Metadata.xls"

# DS 487 documents the horizontal reference as NAD83 / UTM Zone 11N.
DS487_CRS_EPSG = 26911

# Published overall DS 487 geographic extent.
DS487_EXTENT = (-120.511, 32.518, -117.033, 34.494)  # west, south, east, north
DS487_EXTENT_TOLERANCE = 0.25


class USGS_DS487(FetchModule):
    name = "usgs_ds487"
    meta_category = "Bathymetry"
    meta_desc = "USGS Data Series 487: High-Resolution Coastal Bathymetry"
    meta_agency = "USGS"
    meta_resolution = "3 m"
    meta_license = "Public Domain"
    meta_tags = ["california", "bathymetry", "coastal", "usgs", "dem"]

    def __init__(self, update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.force_update = update

        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    @staticmethod
    def _is_plausible_wgs84_bounds(
        bounds: tuple[float, float, float, float],
    ) -> bool:
        """Return True when bounds plausibly intersect the DS 487 footprint."""
        west, south, east, north = bounds

        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            return False

        ds_w, ds_s, ds_e, ds_n = DS487_EXTENT
        tol = DS487_EXTENT_TOLERANCE
        return not (
            east < ds_w - tol
            or west > ds_e + tol
            or north < ds_s - tol
            or south > ds_n + tol
        )

    @staticmethod
    def _clean_value(value: Any) -> Any | None:
        """Convert dataframe values into JSON-safe Python scalars."""
        if value is None:
            return None

        try:
            if bool(value != value):  # NaN / NaT
                return None
        except (TypeError, ValueError):
            pass

        if hasattr(value, "item"):
            try:
                value = value.item()
            except (ValueError, AttributeError):
                pass

        if isinstance(value, float) and not math.isfinite(value):
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        return str(value)

    @staticmethod
    def _normalise_field_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    @staticmethod
    def _normalise_dataset_token(value: object) -> str:
        """Normalize a coverage attribute into something comparable to a DEM id."""
        text = Path(str(value).strip()).stem.lower()
        text = re.sub(r"[^a-z0-9]+", "", text)

        # Legacy GIS names may include processing/coverage suffixes while the
        # downloadable archive is simply e.g. ``sd4.zip``.
        for suffix in (
            "fullcoveragearea",
            "coveragearea",
            "fullcoverage",
            "coverage",
            "finalmosaic",
            "final",
            "dem",
        ):
            if text.endswith(suffix):
                text = text[: -len(suffix)]

        return text

    @classmethod
    def _match_dataset_id(
        cls,
        properties: dict[str, Any],
        dataset_ids: set[str],
    ) -> str | None:
        """Find the downloadable DEM represented by a coverage feature."""
        normalized_ids = {dataset_id.lower(): dataset_id for dataset_id in dataset_ids}

        for value in properties.values():
            if value in (None, ""):
                continue
            token = cls._normalise_dataset_token(value)
            if token in normalized_ids:
                return normalized_ids[token]

        # Conservative fallback for values such as "sd4 final coverage".
        text = " ".join(str(value).lower() for value in properties.values())
        for dataset_id in sorted(dataset_ids, key=len, reverse=True):
            pattern = rf"(?<![a-z0-9]){re.escape(dataset_id.lower())}(?![a-z0-9])"
            if re.search(pattern, text):
                return dataset_id

        return None

    def _archive_url(
        self,
        directory_url: str,
        archive_name: str,
        fallback_url: str,
    ) -> str:
        """Discover a coverage archive URL, with a stable documented fallback."""
        page = core.Fetch(directory_url).fetch_html()
        if page is not None:
            for href in page.xpath('//a[contains(@href, ".zip")]/@href'):
                if Path(href).name.lower() == archive_name.lower():
                    return urljoin(directory_url, href)

        logger.debug(
            "[%s] Could not discover %s from %s; using %s",
            self.name,
            archive_name,
            directory_url,
            fallback_url,
        )
        return fallback_url

    @staticmethod
    def _extract_shapefile(zip_path: Path, output_dir: Path) -> Path:
        """Extract one shapefile dataset safely and return its .shp path."""
        with zipfile.ZipFile(zip_path) as archive:
            shp_members = [
                name for name in archive.namelist() if name.lower().endswith(".shp")
            ]
            if not shp_members:
                raise RuntimeError(f"{zip_path.name} contains no shapefile")

            if len(shp_members) > 1:
                logger.debug(
                    "Coverage archive %s contains multiple shapefiles; using %s",
                    zip_path.name,
                    shp_members[0],
                )

            shp_member = shp_members[0]
            shp_stem = Path(shp_member).stem.lower()
            parent = Path(shp_member).parent

            wanted_suffixes = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix"}
            extracted_shp: Path | None = None

            for member in archive.infolist():
                member_path = Path(member.filename)
                if member.is_dir():
                    continue
                if member_path.parent != parent:
                    continue
                if member_path.stem.lower() != shp_stem:
                    continue
                if member_path.suffix.lower() not in wanted_suffixes:
                    continue

                destination = output_dir / member_path.name
                destination.write_bytes(archive.read(member))
                if member_path.suffix.lower() == ".shp":
                    extracted_shp = destination

        if extracted_shp is None:
            raise RuntimeError(f"Failed to extract shapefile from {zip_path.name}")

        return extracted_shp

    @staticmethod
    def _repair_geometry(geom):
        """Return a valid Shapely geometry when possible."""
        if geom is None or geom.is_empty:
            return None
        if geom.is_valid:
            return geom

        try:
            from shapely import make_valid

            repaired = make_valid(geom)
        except (ImportError, AttributeError):
            repaired = geom.buffer(0)

        if repaired is None or repaired.is_empty or not repaired.is_valid:
            return None
        return repaired

    def _read_coverage_shapefile(self, shp_path: Path) -> list[dict[str, Any]]:
        """Read coverage polygons with pyogrio and transform them to EPSG:4326."""
        try:
            import pyogrio
            from pyproj import CRS, Transformer
            from shapely.geometry import mapping
            from shapely.ops import transform as shapely_transform
        except ImportError as exc:
            raise RuntimeError(
                "USGS_DS487 requires pyogrio, pyproj, and shapely to build FRED"
            ) from exc

        frame = pyogrio.read_dataframe(shp_path)
        if frame.empty:
            return []

        source_crs = frame.crs
        if source_crs is None:
            logger.warning(
                "[%s] %s has no CRS; falling back to EPSG:%d",
                self.name,
                shp_path.name,
                DS487_CRS_EPSG,
            )
            source_crs = CRS.from_epsg(DS487_CRS_EPSG)
        else:
            source_crs = CRS.from_user_input(source_crs)

        target_crs = CRS.from_epsg(4326)
        transformer = None
        if source_crs != target_crs:
            transformer = Transformer.from_crs(
                source_crs,
                target_crs,
                always_xy=True,
            )

        geometry_name = frame.geometry.name
        records: list[dict[str, Any]] = []

        for _, row in frame.iterrows():
            geom = row[geometry_name]
            geom = self._repair_geometry(geom)
            if geom is None:
                logger.warning(
                    "[%s] Skipping empty/invalid coverage geometry", self.name
                )
                continue

            if transformer is not None:
                geom = shapely_transform(transformer.transform, geom)
                geom = self._repair_geometry(geom)
                if geom is None:
                    logger.warning(
                        "[%s] Skipping geometry that became invalid after transform",
                        self.name,
                    )
                    continue

            if not self._is_plausible_wgs84_bounds(geom.bounds):
                logger.warning(
                    "[%s] Skipping implausible transformed bounds %s from %s",
                    self.name,
                    geom.bounds,
                    shp_path.name,
                )
                continue

            properties = {
                str(column): self._clean_value(row[column])
                for column in frame.columns
                if column != geometry_name
            }
            properties = {
                key: value for key, value in properties.items() if value is not None
            }

            records.append(
                {
                    "properties": properties,
                    "geometry": geom,
                    "mapping": mapping(geom),
                }
            )

        return records

    @staticmethod
    def _dem_links(dems_page) -> dict[str, str]:
        """Return ``{dataset_id: absolute_zip_url}`` from the DEM listing."""
        links: dict[str, str] = {}
        for href in dems_page.xpath('//a[contains(@href, ".zip")]/@href'):
            if Path(href).suffix.lower() != ".zip":
                continue
            dataset_id = Path(href).stem
            links[dataset_id] = urljoin(DS487_DEMS_URL, href)
        return links

    @classmethod
    def _first_property(
        cls,
        properties: dict[str, Any],
        candidates: tuple[str, ...],
    ) -> str | None:
        """Return the first non-empty property whose normalized name matches."""
        normalized = {
            cls._normalise_field_name(name): value for name, value in properties.items()
        }
        for candidate in candidates:
            value = normalized.get(cls._normalise_field_name(candidate))
            if value not in (None, ""):
                return str(value).strip()
        return None

    @classmethod
    def _provenance_record(cls, properties: dict[str, Any]) -> dict[str, Any]:
        """Normalize useful native-dataset metadata without assuming a schema."""
        name = cls._first_property(
            properties,
            (
                "dataset",
                "dataset_name",
                "data_name",
                "name",
                "title",
                "filename",
                "file",
            ),
        )
        source = cls._first_property(
            properties,
            (
                "data_source",
                "datasource",
                "source",
                "provider",
                "agency",
                "originator",
            ),
        )
        resolution = cls._first_property(
            properties,
            (
                "resolution",
                "res",
                "grid_resolution",
                "gridres",
                "cell_size",
                "cellsize",
            ),
        )
        data_type = cls._first_property(
            properties,
            ("data_type", "datatype", "type", "dataformat", "format"),
        )
        date = cls._first_property(
            properties,
            ("date", "year", "survey_date", "surveyyear", "pubdate"),
        )

        normalized: dict[str, Any] = {}
        if name:
            normalized["name"] = name
        if source:
            normalized["source"] = source
        if resolution:
            normalized["resolution"] = resolution
        if data_type:
            normalized["data_type"] = data_type
        if date:
            normalized["date"] = date

        # Preserve the legacy fields as well.  They are valuable archival
        # metadata and the whole index contains only 45 final DEM features.
        normalized["legacy"] = properties
        return normalized

    @staticmethod
    def _source_intersects_dem(source_geom, dem_geom) -> bool:
        """Return True for a positive-area overlap, not just a shared boundary."""
        if not source_geom.bounds or not dem_geom.bounds:
            return False
        if not source_geom.intersects(dem_geom):
            return False

        intersection = source_geom.intersection(dem_geom)
        return not intersection.is_empty and intersection.area > 1e-12

    def _provenance_for_dem(
        self,
        dem_geom,
        data_features: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return native-source metadata for polygons overlapping one final DEM."""
        records: list[dict[str, Any]] = []
        seen: set[str] = set()

        for feature in data_features:
            source_geom = feature["geometry"]
            try:
                if not self._source_intersects_dem(source_geom, dem_geom):
                    continue
            except Exception as exc:
                logger.debug(
                    "[%s] Failed provenance intersection test: %s",
                    self.name,
                    exc,
                )
                continue

            record = self._provenance_record(feature["properties"])
            marker = json.dumps(record, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            records.append(record)

        return records

    @staticmethod
    def _summarize_values(
        provenance: list[dict[str, Any]],
        key: str,
    ) -> str:
        values = sorted(
            {
                str(record[key]).strip()
                for record in provenance
                if record.get(key) not in (None, "")
            }
        )
        return "; ".join(values)

    def _download_and_read_coverage(
        self,
        temp_dir: Path,
        *,
        archive_name: str,
        directory_url: str,
        fallback_url: str,
    ) -> list[dict[str, Any]]:
        """Download, safely extract, and read one DS 487 coverage archive."""
        archive_url = self._archive_url(directory_url, archive_name, fallback_url)
        zip_path = temp_dir / archive_name

        logger.debug("[%s] Downloading %s", self.name, archive_url)
        fetched = core.Fetch(archive_url).fetch_file(str(zip_path), verbose=False)
        if not zip_path.exists():
            raise RuntimeError(
                f"Coverage download did not produce {zip_path} (return value: {fetched!r})"
            )

        extract_dir = temp_dir / Path(archive_name).stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        shp_path = self._extract_shapefile(zip_path, extract_dir)
        return self._read_coverage_shapefile(shp_path)

    def update_fred(self):
        """Build FRED from DS 487 DEM polygons and native-data provenance."""
        logger.info("Building FRED index for USGS DS 487 coverage and provenance...")

        dems_page = core.Fetch(DS487_DEMS_URL).fetch_html()
        if dems_page is None:
            logger.error("[%s] Failed to fetch DS 487 DEM listing.", self.name)
            return

        dem_links = self._dem_links(dems_page)
        if not dem_links:
            logger.error(
                "[%s] No DEM ZIP archives found at %s", self.name, DS487_DEMS_URL
            )
            return

        existing_ids = {
            feature.get("properties", {}).get("ID") for feature in self.FRED.features
        }

        try:
            with tempfile.TemporaryDirectory(prefix="fetchez-ds487-") as temp_name:
                temp_dir = Path(temp_name)

                dem_features = self._download_and_read_coverage(
                    temp_dir,
                    archive_name="DEMCoverageAreas.zip",
                    directory_url=DS487_DEM_COVERAGE_DIR_URL,
                    fallback_url=DS487_DEM_COVERAGE_URL,
                )
                data_features = self._download_and_read_coverage(
                    temp_dir,
                    archive_name="DataCoverageAreas.zip",
                    directory_url=DS487_DATA_COVERAGE_DIR_URL,
                    fallback_url=DS487_DATA_COVERAGE_URL,
                )
        except zipfile.BadZipFile as exc:
            logger.error("[%s] Invalid DS 487 coverage ZIP: %s", self.name, exc)
            return
        except Exception as exc:
            logger.error("[%s] Failed to read DS 487 coverage data: %s", self.name, exc)
            return

        if not dem_features:
            logger.error(
                "[%s] No DEM coverage polygons were read from DS 487.", self.name
            )
            return

        if not data_features:
            logger.warning(
                "[%s] No native-data provenance polygons were read; "
                "continuing with DEM coverage only.",
                self.name,
            )

        logger.info(
            "[%s] Read %d DEM coverage polygon(s) and %d native-data polygon(s).",
            self.name,
            len(dem_features),
            len(data_features),
        )

        count = 0
        matched_ids: set[str] = set()

        with tqdm(
            total=len(dem_features),
            desc="Indexing DS 487 coverage",
            disable=self.silent,
        ) as pbar:
            for feature in dem_features:
                properties = feature["properties"]
                dem_geom = feature["geometry"]

                try:
                    dataset_id = self._match_dataset_id(properties, set(dem_links))
                    if dataset_id is None:
                        logger.warning(
                            "[%s] Could not match DEM coverage feature: %s",
                            self.name,
                            properties,
                        )
                        continue

                    if dataset_id in matched_ids:
                        logger.warning(
                            "[%s] Multiple DEM coverage features matched %s; "
                            "keeping the first.",
                            self.name,
                            dataset_id,
                        )
                        continue
                    matched_ids.add(dataset_id)

                    if dataset_id in existing_ids:
                        continue

                    provenance = self._provenance_for_dem(dem_geom, data_features)
                    source_names = self._summarize_values(provenance, "name")
                    source_providers = self._summarize_values(provenance, "source")
                    source_resolutions = self._summarize_values(
                        provenance, "resolution"
                    )

                    # Keep the compact summaries convenient for ordinary FRED
                    # inspection while retaining the full legacy attributes in
                    # Provenance for future archival/debugging use.
                    fred_properties: dict[str, Any] = {
                        "geom": feature["mapping"],
                        "Name": dataset_id,
                        "ID": dataset_id,
                        "Agency": "USGS",
                        "DataLink": dem_links[dataset_id],
                        "MetadataLink": DS487_METADATA_URL,
                        "DataType": "rio",
                        "DataSource": self.name,
                        "Info": "USGS DS 487, 3 m coastal DEM",
                        "SourceCount": len(provenance),
                        "ProvenanceLink": DS487_METADATA_XLS_URL,
                        "ProvenanceMethod": "native coverage polygon intersection",
                    }
                    if source_names:
                        fred_properties["SourceDatasets"] = source_names
                    if source_providers:
                        fred_properties["SourceProviders"] = source_providers
                    if source_resolutions:
                        fred_properties["SourceResolutions"] = source_resolutions
                    if provenance:
                        fred_properties["Provenance"] = json.dumps(
                            provenance,
                            separators=(",", ":"),
                            sort_keys=True,
                            default=str,
                        )

                    self.FRED.add_survey(**fred_properties)
                    existing_ids.add(dataset_id)
                    count += 1
                except Exception as exc:
                    logger.warning(
                        "[%s] Failed to index DEM coverage feature %s: %s",
                        self.name,
                        properties,
                        exc,
                    )
                finally:
                    pbar.update()

        unmatched_dems = set(dem_links) - matched_ids
        if unmatched_dems:
            logger.warning(
                "[%s] %d DEM archive(s) had no matching coverage polygon: %s",
                self.name,
                len(unmatched_dems),
                ", ".join(sorted(unmatched_dems)),
            )

        if len(dem_features) != len(dem_links):
            logger.warning(
                "[%s] Coverage/DEM count mismatch: %d polygon(s), %d DEM archive(s).",
                self.name,
                len(dem_features),
                len(dem_links),
            )

        if count > 0:
            logger.info("Added %d new DS 487 datasets to FRED.", count)
            self.FRED.save()
        else:
            logger.info("No new DS 487 datasets were added to FRED.")

    def run(self):
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info("No matching USGS DS 487 datasets found for this region.")
            return self

        for surv in results:
            data_link = surv.get("DataLink")
            if not data_link:
                continue

            self.add_entry_to_results(
                url=data_link,
                dst_fn=Path(data_link).name,
                data_type=surv.get("DataType", "rio"),
                info=surv.get("Info", ""),
            )

        return self
