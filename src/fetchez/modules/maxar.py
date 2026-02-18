#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
globato.modules.maxar
~~~~~~~~~~~~~~~~~~~~~

Maxar Open Data Program.
Crawls the static STAC catalog on S3 for disaster response imagery.
"""

from fetchez import cli
from .stac import STACModule
import logging

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Fetch high-res disaster imagery from Maxar Open Data.",
    event="Event Name (e.g. 'Kahramanmaras-turkey-earthquake-23'). REQUIRED.",
    visual="Fetch visual (RGB) COGs (default: True).",
    analytic="Fetch analytic (multispectral) COGs.",
)
class MaxarOpenData(STACModule):
    """Maxar Open Data (Static STAC Catalog)."""

    CATALOG_URL = "https://maxar-opendata.s3.amazonaws.com/events/catalog.json"

    def __init__(self, event=None, visual=True, analytic=False, **kwargs):
        super().__init__(url=self.CATALOG_URL, **kwargs)
        self.event_name = event
        self.want_visual = visual
        self.asset_type = "visual" if not analytic else "analytic"

    def run(self):
        if not self.event_name:
            logger.error(
                "Maxar module requires --event name (e.g. 'Libya-Floods-Sept-23')."
            )
            logger.info("Browse events at: https://www.maxar.com/open-data")
            return

        try:
            import pystac
        except ImportError:
            logger.error("Maxar module requires 'pystac'.")
            return

        event_url = self.CATALOG_URL.replace(
            "catalog.json", f"{self.event_name}/catalog.json"
        )
        logger.info(f"Accessing Event Catalog: {self.event_name}")

        try:
            cat = pystac.Catalog.from_file(event_url)
        except Exception:
            logger.error(f"Event '{self.event_name}' not found or URL invalid.")
            return

        logger.info("Crawling catalog... this may take a moment.")
        count = 0
        for item in cat.get_all_items():
            if not self._intersects(item.bbox):
                continue

            if self.asset_type not in item.assets:
                continue

            asset = item.assets[self.asset_type]
            href = asset.href

            dst_fn = f"maxar_{self.event_name}_{item.id}.tif"
            self.add_entry_to_results(href, dst_fn, "raster")
            count += 1

        logger.info(f"Found {count} Maxar scenes intersecting region.")

    def _intersects(self, item_bbox):
        """Simple BBOX intersection test."""

        if not self.region:
            return True
        r = self.region  # w, e, s, n

        if item_bbox[2] < r[0] or item_bbox[0] > r[1]:
            return False

        if item_bbox[3] < r[2] or item_bbox[1] > r[3]:
            return False

        return True
