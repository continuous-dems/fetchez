#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.cusp
~~~~~~~~~~~~~~~~~~~~

Fetch NOAA Continually Updated Shoreline Product (CUSP) data.
Uses the 'Generative Tile' strategy for 5x5 degree tiles.

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import math
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

CUSP_BASE = "https://nsde.ngs.noaa.gov/downloads/"


@cli.cli_opts(
    help_text="NOAA Continually Updated Shoreline Product (CUSP)",
    region="Region to fetch (W/E/S/N)",
)
class CUSP(core.FetchModule):
    """NOAA Continually Updated Shoreline Product (CUSP).

    Data is distributed in 5x5 degree tiles, snapped to 5-degree lines.
    (e.g., N55W135 covers 55N-60N, 135W-140W).
    """

    def __init__(self, **kwargs):
        super().__init__(name="cusp", **kwargs)
        self.title = "NOAA CUSP"
        self.source = "NOAA NGS"
        self.src_srs = "epsg:4326"
        self.data_type = "vector"
        self.format = "zip"

    def run(self):
        """Generate 5x5 degree tile URLs based on the region."""

        if not self.region:
            return []

        w, e, s, n = self.region

        # Snap coordinates to the 5-degree grid (Floor to nearest 5)
        # lat_min = int(math.floor(s / 5.0) * 5)
        # lat_max = int(math.ceil(n / 5.0) * 5)

        lon_min_grid = int(math.floor(w / 5.0) * 5)
        lon_max_grid = int(math.ceil(e / 5.0) * 5)
        lat_min_grid = int(math.floor(s / 5.0) * 5)
        lat_max_grid = int(math.ceil(n / 5.0) * 5)

        logger.info(
            f"Generating CUSP tiles for grid range: Lat {lat_min_grid} to {lat_max_grid}, Lon {lon_min_grid} to {lon_max_grid}"
        )

        for lat in range(lat_min_grid, lat_max_grid + 1, 5):
            for lon in range(lon_min_grid, lon_max_grid + 1, 5):
                # Latitude Part
                lat_char = "N" if lat >= 0 else "S"
                lat_str = f"{lat_char}{abs(lat)}"

                # Longitude Part
                lon_char = "E" if lon >= 0 else "W"
                lon_str = f"{lon_char}{abs(lon):03d}"

                filename = f"{lat_str}{lon_str}.zip"
                url = f"{CUSP_BASE}{filename}"

                self.add_entry_to_results(
                    url=url,
                    dst_fn=filename,
                    data_type="cusp",
                    weight=20.0,
                )

        return self
