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
from urllib.parse import unquote, urlsplit

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
    products="Elevation products: s1m/1m/1_9as/1_3as/1_as/5m/2_as (strict queries)",
    strict_datasets="Raise on rejected or incomplete queries instead of returning partial results",
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
        products: Optional[str] = None,
        strict_datasets: bool = False,
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
        self.products = None
        if products is not None:
            if datasets is not None:
                raise ValueError("Use either products or datasets, not both")
            selected = products.split("/") if isinstance(products, str) else products
            self.products = list(
                dict.fromkeys(str(value).lower() for value in selected)
            )
            if not self.products or any(
                value not in DATASET_ALIASES for value in self.products
            ):
                raise ValueError(f"Unknown TNM products: {products}")
        self.strict_datasets = self.products is not None or bool(
            utils.str2bool(strict_datasets)
        )

    def run(self):
        """Run the TNM fetching module."""

        if self.wgs_region is None or not spatial.region_valid_p(self.wgs_region):
            return []

        # Determine Datasets to query
        dataset_names = []
        if self.products is not None:
            dataset_names = [
                DATASET_CODES[DATASET_ALIASES[value]] for value in self.products
            ]
        elif self.datasets not in (None, "None"):
            try:
                ds_indices = []
                for x in self.datasets.split("/"):
                    if x.lower() in DATASET_ALIASES:
                        ds_indices.append(DATASET_ALIASES[x.lower()])
                    else:
                        ds_indices.append(int(x))
                if self.strict_datasets and any(
                    i < 0 or i >= len(DATASET_CODES) for i in ds_indices
                ):
                    raise ValueError("Dataset index out of range")
                dataset_names = [
                    DATASET_CODES[i] for i in ds_indices if 0 <= i < len(DATASET_CODES)
                ]
            except (ValueError, IndexError):
                if self.strict_datasets:
                    raise ValueError(f"Invalid TNM datasets: {self.datasets}") from None
                logger.warning(
                    f"Could not parse datasets '{self.datasets}'. Using default."
                )

        if not dataset_names:
            dataset_names = ["National Elevation Dataset (NED) 1 arc-second"]

        start = len(self.results)
        try:
            # Query products separately so each entry has an unambiguous product label.
            if self.products is not None:
                for dataset in dataset_names:
                    self._run_query([dataset])
            else:
                self._run_query(dataset_names)
        except Exception:
            del self.results[start:]
            raise
        return self

    def _run_query(self, dataset_names):
        w, e, s, n = self.wgs_region
        bbox_str = f"{w},{s},{e},{n}"
        offset = 0
        expected_total = None
        seen_urls = set()
        dataset = dataset_names[0] if len(dataset_names) == 1 else None
        product = DATASET_PRODUCTS.get(dataset)

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
                if self.strict_datasets:
                    raise RuntimeError("TNM API rejected the requested dataset")
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
                # A broad text search cannot establish a specific product identity.
                product = None
                dataset = None

            if req is None or req.status_code != 200:
                if self.strict_datasets:
                    status = req.status_code if req is not None else "no response"
                    raise RuntimeError(f"TNM API request failed: {status}")
                logger.error(
                    f"TNM API Failed: {req.status_code if req else 'No Response'}"
                )
                break

            if req.text.strip().startswith("{errorMessage"):
                if self.strict_datasets:
                    raise RuntimeError(f"TNM API error: {req.text}")
                logger.error(f"TNM API Error: {req.text}")
                break

            try:
                data = req.json()
                total = data.get("total", 0)
                items = data.get("items", [])
                if self.strict_datasets:
                    if (
                        data.get("errorMessage")
                        or "total" not in data
                        or "items" not in data
                        or not isinstance(total, int)
                        or total < 0
                        or not isinstance(items, list)
                        or offset + len(items) > total
                        or (offset < total and not items)
                    ):
                        raise ValueError(
                            "TNM API returned an incomplete or invalid page"
                        )
                    if expected_total is not None and total != expected_total:
                        raise ValueError("TNM result total changed during pagination")
                    expected_total = total

                for item in items:
                    url = item.get("downloadURL")
                    if not url:
                        if self.strict_datasets:
                            raise ValueError("TNM product has no download URL")
                        continue
                    if self.strict_datasets:
                        if url in seen_urls:
                            raise ValueError(
                                "TNM API repeated a download URL during pagination"
                            )
                        seen_urls.add(url)

                    path = urlsplit(url).path
                    filename = path.rsplit("/", 1)[-1]
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

                    date = item.get("publicationDate", "")
                    project = None
                    if "/Projects/" in path:
                        project = unquote(
                            path.split("/Projects/", 1)[1].split("/", 1)[0]
                        )

                    dst_fn = filename
                    if self.products is not None:
                        # Different projects/versions can share a filename.
                        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
                        dst_fn = f"{product}/{digest}/{filename}"

                    self.add_entry_to_results(
                        url=url,
                        dst_fn=dst_fn,
                        data_type="tnm",
                        format=fmt,
                        bounds=bounds,
                        geometry=geom,
                        date=date,
                        remote_size=item.get("sizeInBytes"),
                        title=item.get("title"),
                        tnm_project=project,
                        tnm_product=product,
                        tnm_dataset=dataset,
                        tnm_source_id=item.get("sourceId"),
                        tnm_publication_date=item.get("publicationDate"),
                        tnm_last_updated=item.get("lastUpdated"),
                        tnm_meta_url=item.get("metaUrl"),
                        tnm_vendor_meta_url=item.get("vendorMetaUrl"),
                    )

            except Exception as e:
                if self.strict_datasets:
                    raise RuntimeError(f"Unable to complete TNM discovery: {e}") from e
                logger.exception(f"Error parsing TNM JSON: {e}")
                break

            offset += len(items) if self.strict_datasets else 100
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
