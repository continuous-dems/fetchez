#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
globato.modules.common.stac
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
from fetchez import core, cli

try:
    import pystac_client

    HAS_STAC = True
except ImportError:
    HAS_STAC = False

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
class STACModule(core.FetchModule):
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

    def run(self):
        if not HAS_STAC:
            logger.error(
                "STACModule requires 'pystac-client'. Install it with: pip install pystac-client"
            )
            return

        if not self.region:
            logger.error("Region is required for STAC search.")
            return

        logger.info(f"Querying STAC API: {self.api_url}")

        try:
            client = pystac_client.Client.open(self.api_url)
            # w, e, s, n = self.reigon
            # bbox = (w, s, e, n)
            search_params = {
                "bbox": self.region,
                "max_items": self.limit,
            }

            if self.collections:
                search_params["collections"] = self.collections

            if self.datetime:
                search_params["datetime"] = self.datetime

            if self.cloud_cover is not None:
                search_params["query"] = {"eo:cloud_cover": {"lt": self.cloud_cover}}

            search = client.search(**search_params)
            items = list(search.items())

            if not items:
                logger.warning("No items found matching criteria.")
                return

            logger.info(f"Found {len(items)} STAC items.")

            count = 0
            for item in items:
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
                    href = asset.href

                    date_str = (
                        item.datetime.strftime("%Y%m%d") if item.datetime else "nodate"
                    )
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
                    count += 1

            logger.info(f"Queued {count} assets for download.")

        except Exception as e:
            logger.error(f"STAC Query failed: {e}", exc_info=True)
