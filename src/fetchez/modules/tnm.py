#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tnm
~~~~~~~~~~~~~~~~~~~~

Fetch elevation data from The National Map (TNM) API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import datetime
import logging
from typing import Optional, List, Any

from fetchez import core
from fetchez import utils
from fetchez import spatial
from fetchez import cli

logger = logging.getLogger(__name__)

TNM_API_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products?"

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
class TheNationalMap(core.FetchModule):
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
        self.datasets = datasets
        self.date_type = date_type
        self.date_start = date_start
        self.date_end = date_end

    def run(self):
        """Run the TNM fetching module."""

        if self.region is None or not spatial.region_valid_p(self.region):
            return []

        # Convert region tuple to string for API: "xmin,ymin,xmax,ymax"
        # Note: TNM uses comma-separated bbox
        w, e, s, n = self.region
        bbox_str = f"{w},{s},{e},{n}"

        offset = 0
        total = 0

        # Determine Datasets to query
        dataset_names = []
        if self.datasets is not None:
            try:
                ds_indices = [int(x) for x in self.datasets.split("/")]
                dataset_names = [
                    DATASET_CODES[i] for i in ds_indices if 0 <= i < len(DATASET_CODES)
                ]
            except (ValueError, IndexError):
                logger.warning(
                    f"Could not parse datasets '{self.datasets}'. Using default."
                )

        # Default to NED 1 arc-second if nothing valid selected
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
                )  # YYYYMMDD
                params["dateType"] = self.date_type

            req = core.Fetch(TNM_API_PRODUCTS_URL).fetch_req(
                params=params, timeout=60, read_timeout=60
            )

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
                    if item_bbox:
                        bounds = (
                            item_bbox.get("minX"),
                            item_bbox.get("maxX"),
                            item_bbox.get("minY"),
                            item_bbox.get("maxY"),
                        )

                    self.add_entry_to_results(
                        url=url,
                        dst_fn=filename,
                        data_type="tnm",
                        format=fmt,
                        bounds=bounds,
                        date=item.get("publicationDate"),
                        remote_size=item.get("sizeInBytes"),
                        title=item.get("title"),
                    )

            except Exception as e:
                logger.error(f"Error parsing TNM JSON: {e}")
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
    """Shortcut for fetching Lidar Point Clouds (LAZ)."""

    def __init__(self, **kwargs):
        # Index 11 (LPC) + Format Filter
        super().__init__(datasets="11", formats="LAZ", **kwargs)
