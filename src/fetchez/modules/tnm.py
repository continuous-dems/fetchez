#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tnm
~~~~~~~~~~~~~~~~~~~

Fetch elevation data from The National Map (TNM) API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from typing import Optional

from shapely.geometry import box

from fetchez import core
from fetchez.modules import FetchModule
from fetchez import utils
from fetchez import spatial
from fetchez import cli

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
]
DATASET_ALIASES = {
    "1m": 2,
    "1_9as": 4,
    "1_3as": 3,
    "1_as": 1,
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

    def run(self):
        """Run the TNM fetching module."""

        if self.wgs_region is None or not spatial.region_valid_p(self.wgs_region):
            return []

        w, e, s, n = self.wgs_region
        bbox_str = f"{w},{s},{e},{n}"

        offset = 0
        total = 0

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
                req
                and "All dataset queries failed" in req.text
                and "datasets" in params
            ):
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
                logger.error(
                    f"TNM API Failed: {req.status_code if req else 'No Response'}"
                )
                break

            if req.text.strip().startswith("{errorMessage"):
                logger.error(f"TNM API Error: {req.text}")
                break

            try:
                data = req.json()
                total = data.get("total", 0)
                items = data.get("items", [])

                for item in items:
                    url = item.get("downloadURL")
                    if not url:
                        continue

                    filename = url.split("/")[-1]
                    fmt = item.get("format", "Unknown")

                    item_bbox = item.get("boundingBox", {})
                    bounds = None
                    geom = None
                    if item_bbox:
                        bounds = (
                            item_bbox.get("minX"),
                            item_bbox.get("maxX"),
                            item_bbox.get("minY"),
                            item_bbox.get("maxY"),
                        )
                        geom = box(bounds[0], bounds[2], bounds[1], bounds[3])

                    # Extract the tile footprint or project ID based on dataset type
                    # this is all redundant now, but keeping in case useful.
                    if (
                        "ned19" in filename.lower()
                        or "opr" in filename.lower()
                        or "lpc" in filename.lower()
                    ):
                        _fn_bn = "_".join(filename.split("_")[:-1])
                    elif bounds:
                        _fn_bn = f"{round(bounds[0], 4)}_{round(bounds[1], 4)}_{round(bounds[2], 4)}_{round(bounds[3], 4)}"
                    else:
                        _fn_bn = item.get("title", filename)

                    date = item.get("publicationDate", "")
                    if bounds:
                        _bounds_str = f"{round(bounds[0], 4)}_{round(bounds[1], 4)}_{round(bounds[2], 4)}_{round(bounds[3], 4)}"
                        _project_id = "/".join(item.get("title", ""))
                        _fn_bn = f"{_bounds_str}_{_project_id}"
                    else:
                        _fn_bn = item.get("title", filename)

                    date = item.get("publicationDate", "")
                    project = None
                    if "/Projects/" in url:
                        project = url.split("/Projects/", 1)[1].split("/", 1)[0]

                    self.add_entry_to_results(
                        url=url,
                        dst_fn=filename,
                        data_type="tnm",
                        format=fmt,
                        bounds=bounds,
                        geometry=geom,
                        date=date,
                        remote_size=item.get("sizeInBytes"),
                        title=item.get("title"),
                        tnm_project=project,
                        tnm_source_id=item.get("sourceId"),
                        tnm_publication_date=item.get("publicationDate"),
                        tnm_last_updated=item.get("lastUpdated"),
                        tnm_meta_url=item.get("metaUrl"),
                        tnm_vendor_meta_url=item.get("vendorMetaUrl"),
                    )

            except Exception as e:
                logger.exception(f"Error parsing TNM JSON: {e}")
                break

            offset += 100
            if offset >= total:
                break

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
