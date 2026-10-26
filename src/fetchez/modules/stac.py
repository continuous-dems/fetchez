#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
globato.modules.stac
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generic STAC (SpatioTemporal Asset Catalog) Module.
Enables fetching data from any STAC API (e.g. Microsoft Planetary Computer, Earth Search).

Dependencies:
    pip install pystac pystac-client

:copyright: (c) 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from fetchez import cli
from fetchez.modules import FetchModule

try:
    import pystac_client

    HAS_STAC = True
except ImportError:
    HAS_STAC = False

try:
    import planetary_computer

    HAS_PC = True
except ImportError:
    HAS_PC = False

try:
    import boto3
    from botocore.exceptions import NoCredentialsError, BotoCoreError

    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Fetch data from a STAC API.",
    url="STAC API Endpoint URL.",
    collections="Comma-separated list of Collection IDs.",
    assets="Comma-separated list of Asset Keys to fetch (e.g. 'visual,B04').",
    date="Date range (e.g. '2023-01-01/2023-01-31').",
    cloud_cover="Maximum cloud cover percentage (0-100).",
    limit="Max number of items to fetch.",
)
class STACModule(FetchModule):
    name = "stac"
    meta_category = "Generic"
    meta_desc = "Generic STAC API Fetcher (SpatioTemporal Asset Catalog)"
    meta_agency = "Various"
    meta_tags = ["stac", "api", "catalog", "spatiotemporal", "json", "cloud-native"]
    meta_region = "Global"
    meta_resolution = "Variable"
    meta_license = "Varies"
    meta_urls = {
        "spec": "https://stacspec.org/",
        "browser": "https://radiantearth.github.io/stac-browser/",
    }

    """Generic fetcher for STAC APIs."""

    DEFAULT_API = "https://earth-search.aws.element84.com/v1"

    def __init__(
        self,
        url=None,
        collections=None,
        assets=None,
        date=None,
        cloud_cover=None,
        limit=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_url = url or self.DEFAULT_API
        self.collections = collections.split(",") if collections else None
        self.asset_keys = assets.split(",") if assets else None
        self.datetime = date
        self.cloud_cover = float(cloud_cover) if cloud_cover is not None else None
        self.limit = int(limit) if limit else 500

    def _open_catalog(self):
        """Open STAC catalog and configure authentication."""
        return pystac_client.Client.open(self.api_url)

    def _build_search(self):
        """Construct search using region and query settings."""
        w, e, s, n = self.wgs_region
        bbox = (w, s, e, n)
        search_params = {
            "bbox": bbox,  # self.wgs_region,
            "max_items": self.limit,
        }

        if self.collections:
            search_params["collections"] = self.collections

        if self.datetime:
            search_params["datetime"] = self.datetime

        if self.cloud_cover is not None:
            search_params["query"] = {"eo:cloud_cover": {"lt": self.cloud_cover}}

        return search_params

    def _select_assets(self, item):
        """Choose matching assets from an item."""
        keys_to_fetch = self.asset_keys

        if not keys_to_fetch:
            available = item.assets.keys()
            if "visual" in available:
                keys_to_fetch = ["visual"]
            elif "data" in available:
                keys_to_fetch = ["data"]
            elif "analytic" in available:
                keys_to_fetch = ["analytic"]
            else:
                keys_to_fetch = list(available)

        for key in keys_to_fetch:
            if key not in item.assets:
                continue

            asset = item.assets[key]

            yield key, asset

    def _resolve_asset_url(self, asset):
        """Resolve or sign asset URLs as required."""
        href = asset.href
        if "planetarycomputer" in self.api_url:
            if HAS_PC:
                href = planetary_computer.sign(href)
            else:
                logger.warning(
                    "Planetary Computer URL detected, but 'planetary-computer' "
                    "library is missing. Download may fail with 403 Forbidden."
                )
        elif href.startswith("s3://"):
            if HAS_BOTO3:
                try:
                    import urllib.parse

                    parsed = urllib.parse.urlparse(href)
                    bucket_name = parsed.netloc
                    object_key = parsed.path.lstrip("/")

                    s3_client = boto3.client("s3")
                    # Generate a presigned URL valid for 1 hour (3600 seconds)
                    href = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": object_key},
                        ExpiresIn=3600,
                    )
                except (NoCredentialsError, BotoCoreError) as e:
                    logger.warning(
                        f"Could not presign S3 URL {href}: {e}. Falling back to unsigned HTTPS."
                    )
                    path_parts = href.replace("s3://", "").split("/", 1)
                    if len(path_parts) == 2:
                        href = (
                            f"https://{path_parts[0]}.s3.amazonaws.com/{path_parts[1]}"
                        )
            else:
                logger.warning(
                    "boto3 is missing. Cannot presign S3 URL. Falling back to unsigned HTTPS."
                )
                path_parts = href.replace("s3://", "").split("/", 1)
                if len(path_parts) == 2:
                    # Fallback to a valid virtual-hosted style AWS URL
                    href = f"https://{path_parts[0]}.s3.amazonaws.com/{path_parts[1]}"

        return href

    def _asset_to_entry(self, item, key, asset):
        """Convert an asset into a Fetchez entry."""

        href = self._resolve_asset_url(asset)

        date_str = item.datetime.strftime("%Y%m%d") if item.datetime else "nodate"

        ext = os.path.splitext(href)[1]
        if not ext:
            ext = ".tif"

        dst_fn = f"{item.collection_id}_{date_str}_{item.id}_{key}{ext}"

        self.add_entry_to_results(
            url=href,
            dst_fn=dst_fn,
            data_type="raster",
            stac_id=item.id,
            stac_date=date_str,
        )

    def run(self):
        """Discover matching items and register their assets."""
        if not HAS_STAC:
            logger.error(
                "STACModule requires 'pystac-client'. Install it with: pip install pystac-client"
            )
            return

        if not self.wgs_region:
            logger.error("Region is required for STAC search.")
            return

        logger.info(f"Querying STAC API: {self.api_url}")

        try:
            client = self._open_catalog()
            search = client.search(**self._build_search())

            for item in search.items():
                for key, asset in self._select_assets(item):
                    self._asset_to_entry(item, key, asset)

        except Exception:
            self._discovery_failed = True
            logger.exception("STAC discovery failed")

        return self


@cli.cli_opts(
    help_text="USGS 3DEP Seamless DEMs via Planetary Computer STAC",
)
class STAC_3DEP_Seamless(STACModule):
    name = "stac_3dep"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Seamless DEMs (1/3 arc-sec, 1 arc-sec, 10m) via STAC"
    meta_aliases = ["stac_ned", "pc_3dep"]

    def __init__(self, **kwargs):
        # 3DEP seamless DEMs live in the '3dep-seamless' collection
        kwargs.pop("url")
        kwargs.pop("collections")
        kwargs.pop("assets")
        kwargs.pop("limit")
        super().__init__(
            url="https://planetarycomputer.microsoft.com/api/stac/v1",
            collections="3dep-seamless",
            assets="data",
            limit=1000,
            **kwargs,
        )


@cli.cli_opts(
    help_text="USGS 3DEP Lidar COPC via Planetary Computer STAC",
)
class STAC_3DEP_Lidar(STACModule):
    name = "stac_lidar"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Lidar Point Clouds (COPC/LAZ) via STAC"
    meta_aliases = ["stac_laz", "pc_lidar"]

    def __init__(self, **kwargs):
        # 3DEP Lidar lives in the '3dep-lidar-copc' collection
        kwargs.pop("url")
        kwargs.pop("collections")
        kwargs.pop("assets")
        kwargs.pop("limit")
        super().__init__(
            url="https://planetarycomputer.microsoft.com/api/stac/v1",
            collections="3dep-lidar-copc",
            assets="data",
            limit=1000,
            **kwargs,
        )
