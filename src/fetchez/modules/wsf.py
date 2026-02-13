#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.wsf
~~~~~~~~~~~~~~~~~~~~

Fetch World Settlement Footprint (WSF) 2019 data from the
German Aerospace Center (DLR).

Data is organized in 2x2 degree GeoTIFF tiles.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from typing import Optional, List, Dict

from fetchez import core
from fetchez import utils
from fetchez import fred
from fetchez import cli

logger = logging.getLogger(__name__)

WSF_BASE_URL = 'https://download.geoservice.dlr.de/WSF2019/files/'

# =============================================================================
# WSF Module
# =============================================================================
@cli.cli_opts(
    help_text="World Settlement Footprint (WSF) 2019",
    update="Force update of the local index (FRED)"
)

class WSF(core.FetchModule):
    """Fetch World Settlement Footprint (WSF) 2019 data.

    The WSF 2019 is a 10m resolution binary mask outlining the
    extent of human settlements globally.
    """

    def __init__(self, update: bool = False, **kwargs):
        super().__init__(name='wsf', **kwargs)
        self.force_update = update

        # Initialize FRED (Local Index)
        self.fred = fred.FRED(name='wsf')

        # Check if we need to populate/update the index
        if self.force_update or len(self.fred.features) == 0:
            self.update_index()


    def update_index(self):
        """Crawl the DLR directory and update the FRED index."""

        logger.info("Updating WSF Index from DLR (this may take a moment)...")

        # Fetch the HTML directory listing
        page = core.Fetch(WSF_BASE_URL).fetch_html()

        if page is None:
            logger.error("Failed to fetch WSF directory listing.")
            return

        # Clear existing
        self.fred.features = []

        # Find all TIF links
        # Filename format: WSF2019_v1_{minx}_{miny}.tif
        # Example: WSF2019_v1_-74_40.tif
        rows = page.xpath('//a[contains(@href, ".tif")]/@href')

        count = 0
        for row in rows:
            filename = row.split('/')[-1]
            sid = filename.replace('.tif', '')

            # Skip overview COGs if present
            if 'cog' in sid.lower(): continue

            try:
                # Parse spatial info from filename
                parts = sid.split('_')
                # usually [WSF2019, v1, x, y]
                # x and y are the lower-left corner
                x = int(parts[-2])
                y = int(parts[-1])

                # Tiles are 2x2 degrees
                w, e = x, x + 2
                s, n = y, y + 2

                # Create GeoJSON Polygon
                geom = {
                    "type": "Polygon",
                    "coordinates": [[
                        [w, s], [e, s], [e, n], [w, n], [w, s]
                    ]]
                }

                self.fred.add_survey(
                    geom=geom,
                    Name=sid,
                    ID=sid,
                    Agency='DLR',
                    DataLink=f"{WSF_BASE_URL}{filename}",
                    DataType='WSF',
                    Date='2019',
                    Info='World Settlement Footprint 2019 (10m)'
                )
                count += 1

            except (IndexError, ValueError):
                logger.debug(f"Skipping unparseable file: {filename}")
                continue

        logger.info(f"Indexed {count} WSF tiles.")
        self.fred.save()

    def run(self):
        """Run the WSF fetching module."""

        if self.region is None:
            return []

        # Query FRED
        results = self.fred.search(region=self.region)

        if not results:
            logger.info("No WSF tiles found in this region.")
            return

        for item in results:
            url = item.get('DataLink')
            name = item.get('Name')

            if url:
                self.add_entry_to_results(
                    url=url,
                    dst_fn=os.path.basename(url),
                    data_type='wsf_tif',
                    agency='DLR',
                    title=name,
                    license='CC-BY 4.0'
                )

        return self
