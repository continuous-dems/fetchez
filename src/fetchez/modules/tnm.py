#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tnm
~~~~~~~~~~~~~~~~~~~

Fetch elevation data from The National Map (TNM) API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import hashlib
import logging
from typing import Optional

from fetchez import core
from fetchez.modules import FetchModule
from fetchez import utils
from fetchez import spatial
from fetchez import cli
from fetchez.modules import tnm_ned, tnm_raster
from fetchez.modules.tnm_wesm import WESM

logger = logging.getLogger(__name__)

TNM_API_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products?"
TNM_API_DATASETS_URL = "https://tnmaccess.nationalmap.gov/api/v1/datasets?"

DATASET_CODES = [
    "National Boundary Dataset (NBD)",
    "National Elevation Dataset (NED) 1 arc-second",
    "Digital Elevation Model (DEM) 1 meter",
    "National Elevation Dataset (NED) 1/3 arc-second",
    "National Elevation Dataset (NED) 1/9 arc-second",
    "National Elevation Dataset (NED) Alaska 2 arc-second",
    "Alaska IFSAR 5 meter DEM",
    "National Elevation Dataset (NED) 1/3 arc-second - Contours",
    "Original Product Resolution (OPR) Digital Elevation Model (DEM)",
    "Ifsar Digital Surface Model (DSM)",
    "Ifsar Orthorectified Radar Image (ORI)",
    "Lidar Point Cloud (LPC)",
    "Historical Topographic Maps",
    "National Hydrography Dataset Plus High Resolution (NHDPlus HR)",
    "National Hydrography Dataset (NHD) Best Resolution",
    "National Watershed Boundary Dataset (WBD)",
    "Map Indices",
    "National Geographic Names Information System (GNIS)",
    "Small-scale Datasets - Boundaries",
    "Small-scale Datasets - Contours",
    "Small-scale Datasets - Hydrography",
    "Small-scale Datasets - Transportation",
    "National Structures Dataset (NSD)",
    "Combined Vector",
    "National Transportation Dataset (NTD)",
    "US Topo Current",
    "US Topo Historical",
    "Land Cover - Woodland",
    "3D Hydrography Program (3DHP)",
    "Seamless 1-m DEM (S1M)",
]
DATASET_ALIASES = {
    "1m": 2,
    "1_9as": 4,
    "1_3as": 3,
    "1_as": 1,
    "2_as": 5,
    "5m": 6,
    "s1m": 29,
}
DATASET_PRODUCTS = {
    DATASET_CODES[index]: alias for alias, index in DATASET_ALIASES.items()
}


# =============================================================================
# The National Map Module
# =============================================================================
@cli.cli_opts(
    help_text="USGS The National Map (TNM) Elevation Products",
    datasets="Slash-separated indices of datasets to fetch (e.g. '1/3')",
    formats="Filter by file format (e.g. GeoTIFF, LAZ)",
    extents="Filter by extent (e.g. '1 x 1 degree')",
    q="Free text search query",
    date_start="Start date (YYYY-MM-DD)",
    date_end="End date (YYYY-MM-DD)",
    strict_datasets="Fail instead of broadening a rejected dataset query",
    source_coverage="Attach authoritative USGS source coverage",
)
class TheNationalMap(FetchModule):
    name = "tnm"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Products (NED, Lidar, Hydro) via The National Map"
    meta_agency = "USGS"
    meta_tags = ["usgs", "ned", "3dep", "lidar", "usa", "elevation"]
    meta_region = "USA"
    meta_resolution = "Varies (1m - 1 arc-second)"
    meta_license = "Public Domain (USGS)"
    meta_urls = {
        "home": "https://apps.nationalmap.gov/",
        "api": "https://tnmaccess.nationalmap.gov/api/v1/docs/",
    }

    """Fetch elevation data from The National Map.

    Default behavior fetches 'NED 1 arc-second' if no dataset is specified.

    Dataset Codes (indices for --datasets):
      1: NED 1 arc-second
      2: DEM 1 meter
      3: NED 1/3 arc-second
      4: NED 1/9 arc-second
      8: Original Product Resolution (OPR)
      11: Lidar Point Cloud (LPC)
    """

    def __init__(
        self,
        datasets: Optional[str] = None,
        formats: Optional[str] = None,
        extents: Optional[str] = None,
        q: Optional[str] = None,
        date_type: Optional[str] = "dateCreated",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        dedupe: bool = True,
        strict_datasets: bool = False,
        source_coverage: bool = False,
        **kwargs,
    ):
        super().__init__(name="tnm", **kwargs)
        self.q = q
        self.formats = formats
        self.extents = extents
        self.datasets = str(datasets)
        self.date_type = date_type
        self.date_start = date_start
        self.date_end = date_end
        self.dedupe = utils.str2bool(dedupe)
        if self.dedupe is None:
            self.dedupe = True
        self.strict_datasets = utils.str2bool(strict_datasets)
        if self.strict_datasets is None:
            self.strict_datasets = False
        self.source_coverage = utils.str2bool(source_coverage)
        if self.source_coverage is None:
            self.source_coverage = False

    def run(self):
        """Run the TNM fetching module."""

        if self.wgs_region is None or not spatial.region_valid_p(self.wgs_region):
            return []

        w, e, s, n = self.wgs_region
        bbox_str = f"{w},{s},{e},{n}"

        offset = 0
        expected_total: Optional[int] = None

        # Determine Datasets to query
        dataset_names = []
        if self.datasets is not None:
            try:
                ds_indices = []
                for x in self.datasets.split("/"):
                    if x.lower() in DATASET_ALIASES:
                        ds_indices.append(DATASET_ALIASES[x.lower()])
                    else:
                        ds_indices.append(int(x))
                dataset_names = [
                    DATASET_CODES[i] for i in ds_indices if 0 <= i < len(DATASET_CODES)
                ]
            except (ValueError, IndexError):
                logger.warning(
                    f"Could not parse datasets '{self.datasets}'. Using default."
                )

        if not dataset_names:
            dataset_names = ["National Elevation Dataset (NED) 1 arc-second"]
        product = (
            DATASET_PRODUCTS.get(dataset_names[0]) if len(dataset_names) == 1 else None
        )

        best_tiles = {}
        all_tiles = []
        while True:
            params = {
                "bbox": bbox_str,
                "max": 100,
                "offset": offset,
                "datasets": ",".join(dataset_names),
            }

            if self.q:
                params["q"] = str(self.q)
            if self.formats:
                params["prodFormats"] = self.formats.replace("/", ",")
            if self.extents:
                params["prodExtents"] = self.extents.replace("/", ",")

            if self.date_start:
                params["start"] = self.date_start
                params["end"] = (
                    self.date_end if self.date_end else utils.this_date()[:8]
                )
                params["dateType"] = self.date_type

            req = core.Fetch(TNM_API_PRODUCTS_URL).fetch_req(params=params)

            if (
                req is not None
                and "All dataset queries failed" in req.text
                and "datasets" in params
            ):
                if self.strict_datasets or self.source_coverage:
                    raise RuntimeError("TNM API rejected the strict dataset query")
                logger.warning(
                    "USGS rejected the strict dataset strings. Retrying with broad text search..."
                )

                params.pop("datasets")

                fallback_q = params.get("q", "") + " " + " ".join(dataset_names)
                fallback_q = fallback_q.replace(
                    "National Elevation Dataset (NED)", ""
                ).strip()
                params["q"] = fallback_q

                req = core.Fetch(TNM_API_PRODUCTS_URL).fetch_req(params=params)

            if req is None or req.status_code != 200:
                status = req.status_code if req is not None else "no response"
                raise RuntimeError(f"TNM API request failed: {status}")

            try:
                try:
                    data = req.json()
                except Exception as exc:
                    raise RuntimeError("TNM API returned invalid JSON") from exc
                if not isinstance(data, dict):
                    raise RuntimeError("TNM API returned an invalid response")
                if data.get("errorMessage"):
                    raise RuntimeError(f"TNM API error: {data['errorMessage']}")
                if "total" not in data or "items" not in data:
                    raise RuntimeError("TNM API response is missing total or items")
                total = int(data["total"])
                items = data["items"]
                if total < 0 or not isinstance(items, list):
                    raise RuntimeError("TNM API returned an invalid result page")
                if expected_total is None:
                    expected_total = total
                elif total != expected_total:
                    raise RuntimeError(
                        "TNM API result total changed during pagination: "
                        f"{expected_total} to {total}"
                    )
                if offset > total or len(items) > total - offset:
                    raise RuntimeError("TNM API returned an invalid result page")
                if offset < total and not items:
                    raise RuntimeError(
                        f"TNM API pagination stopped after {offset} of {total} products"
                    )

                for item in items:
                    if not isinstance(item, dict):
                        raise RuntimeError("TNM API returned an invalid product entry")
                    url = item.get("downloadURL")
                    if not isinstance(url, str) or not url.strip():
                        raise RuntimeError("TNM product is missing its download URL")

                    filename = url.split("/")[-1]
                    fmt = item.get("format", "Unknown")

                    item_bbox = item.get("boundingBox", {})
                    bounds = None
                    if item_bbox:
                        bounds = (
                            item_bbox.get("minX"),
                            item_bbox.get("maxX"),
                            item_bbox.get("minY"),
                            item_bbox.get("maxY"),
                        )

                    # Extract the tile footprint or project ID based on dataset type
                    if (
                        "ned19" in filename.lower()
                        or "opr" in filename.lower()
                        or "lpc" in filename.lower()
                    ):
                        fn_bn = "_".join(filename.split("_")[:-1])
                    elif bounds:
                        fn_bn = f"{round(bounds[0], 4)}_{round(bounds[1], 4)}_{round(bounds[2], 4)}_{round(bounds[3], 4)}"
                    else:
                        fn_bn = item.get("title", filename)

                    # date = item.get("publicationDate", "")
                    # if bounds:
                    #     bounds_str = f"{round(bounds[0], 4)}_{round(bounds[1], 4)}_{round(bounds[2], 4)}_{round(bounds[3], 4)}"
                    #     project_id = "/".join(item.get("title", ""))
                    #     fn_bn = f"{bounds_str}_{project_id}"
                    # else:
                    #     fn_bn = item.get("title", filename)

                    date = item.get("publicationDate", "")
                    project = None
                    if "/Projects/" in url:
                        project = url.split("/Projects/", 1)[1].split("/", 1)[0]

                    dst_fn = filename
                    if not self.dedupe:
                        url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
                        dst_fn = f"{url_hash}/{filename}"

                    item_data = {
                        "url": url,
                        "dst_fn": dst_fn,
                        "data_type": "tnm",
                        "format": fmt,
                        "bounds": bounds,
                        "date": date,
                        "remote_size": item.get("sizeInBytes"),
                        "title": item.get("title"),
                        "tnm_project": project,
                        "tnm_product": product,
                        "tnm_source_id": item.get("sourceId"),
                        "tnm_publication_date": item.get("publicationDate"),
                        "tnm_last_updated": item.get("lastUpdated"),
                        "tnm_meta_url": item.get("metaUrl"),
                        "tnm_vendor_meta_url": item.get("vendorMetaUrl"),
                    }
                    if not self.dedupe:
                        all_tiles.append(item_data)
                        continue

                    # Check if we already have this tile and compare dates
                    if fn_bn not in best_tiles:
                        best_tiles[fn_bn] = item_data
                    else:
                        existing_date = best_tiles[fn_bn]["date"]
                        if date and date > existing_date:
                            best_tiles[fn_bn] = item_data

            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError("Error parsing TNM API response") from exc

            offset += len(items)
            if offset >= total:
                break

        tiles = list(best_tiles.values()) if self.dedupe else all_tiles
        if self.source_coverage and tiles:
            unsupported = set(dataset_names).difference(
                {
                    DATASET_CODES[2],
                    DATASET_CODES[4],
                    DATASET_CODES[6],
                    DATASET_CODES[29],
                }
            )
            if unsupported:
                raise ValueError(
                    "TNM source coverage supports only S1M, 1 m, 5 m and 1/9 arc-second DEMs"
                )
            if len(dataset_names) != 1:
                raise ValueError("TNM source coverage requires one dataset per module")
            if product in {"s1m", "5m"}:
                tiles = tnm_raster.add_source_coverage(tiles, self.wgs_region)
            elif product == "1_9as":
                tiles = tnm_ned.add_source_coverage(tiles, self.wgs_region)
            else:
                tiles = WESM.add_source_coverage(
                    tiles, self.wgs_region, require_year=True
                )
        for tile_data in tiles:
            self.add_entry_to_results(**tile_data)

        return self


# =============================================================================
# Shortcuts (Subclasses)
# =============================================================================
@cli.cli_opts(
    help_text="National Elevation Dataset (NED) / 3DEP DEMs",
    res="Resolution: '13' (Default: 1 & 1/3 arc-sec), '1m' (1-meter), '1', '1/3', or 'all'",
)
class NED(TheNationalMap):
    name = "ned"
    meta_category = "Topography"
    meta_desc = 'USGS Seamless DEMs (1m, 1/3", 1")'
    meta_aliases = ["3dep_dem", "NED"]

    """
    Shortcut for fetching USGS NED / 3DEP DEMs at various resolutions.

    Resolutions (--res):
      13    : Fetch both 1 arc-second and 1/3 arc-second (Default)
      1m    : Fetch 1-meter DEMs (High Res)
      1/3   : Fetch 1/3 arc-second only
      1     : Fetch 1 arc-second only
      all   : Fetch 1 arc-sec, 1/3 arc-sec, AND 1-meter
    """

    def __init__(self, res: str = "13", **kwargs):
        # Map resolution strings to TNM Dataset Indices
        # 1 = NED 1 arc-sec
        # 2 = DEM 1 meter
        # 3 = NED 1/3 arc-sec

        mapping = {
            "13": "1/3",  # Standard seamless (Old Default)
            "1m": "2",  # High res
            "1": "1",  # Coarse
            "1/3": "3",  # Standard
            "all": "1/2/3",  # Everything
        }

        selected_datasets = mapping.get(res, "1/3")

        super().__init__(datasets=selected_datasets, **kwargs)


@cli.cli_opts(help_text="USGS 3DEP Lidar Point Clouds (LAZ)")
class TNM_LAZ(TheNationalMap):
    name = "3dep"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Lidar Point Clouds (LAZ)"
    meta_aliases = ["3dep_lidar"]

    """Shortcut for fetching Lidar Point Clouds (LAZ)."""

    def __init__(self, **kwargs):
        # Index 11 (LPC) + Format Filter
        super().__init__(datasets="11", formats="LAZ", **kwargs)
