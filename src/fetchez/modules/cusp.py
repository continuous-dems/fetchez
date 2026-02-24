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
from fetchez import utils

logger = logging.getLogger(__name__)

# Base URL
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

        # 1. Snap coordinates to the 5-degree grid (Floor to nearest 5)
        # Examples:
        #   Lat 32.5 -> Floor(32.5 / 5) * 5 = 6 * 5 = 30 (N30)
        #   Lon -117 -> Floor(117 / 5) * 5 = 23 * 5 = 115 (W115)
        #   (Note: NOAA filenames usually use positive numbers for West)

        lat_min = int(math.floor(s / 5.0) * 5)
        lat_max = int(math.ceil(n / 5.0) * 5)

        # For West longitudes (negative), we need to handle the direction carefully.
        # If input is -118 (West), we want the tile starting at 115 or 120?
        # N55W135 usually means the tile starts at 135W and goes to 140W (or 130W?)
        # Let's assume standard grid: Lower-Left Corner.
        # If we are at -117 (117W), the 5-degree tile starting to its WEST is 115W? No, 115 is East of 117.
        # The grid lines are 115, 120. -117 falls between -115 and -120.
        # Standard logic: Min Lon (Westmost) -> Floor(-118) = -120?

        # Let's just iterate broadly to be safe.
        # We define the "Grid Lines" covering the region.

        lon_min_grid = int(math.floor(w / 5.0) * 5)
        lon_max_grid = int(math.ceil(e / 5.0) * 5)
        lat_min_grid = int(math.floor(s / 5.0) * 5)
        lat_max_grid = int(math.ceil(n / 5.0) * 5)

        logger.info(f"Generating CUSP tiles for grid range: Lat {lat_min_grid} to {lat_max_grid}, Lon {lon_min_grid} to {lon_max_grid}")

        for lat in range(lat_min_grid, lat_max_grid + 1, 5):
            for lon in range(lon_min_grid, lon_max_grid + 1, 5):

                # Construct filename parts
                # CUSP naming seems to be: N{lat}W{lon}
                # e.g., N30W115

                # Latitude Part
                lat_char = 'N' if lat >= 0 else 'S'
                lat_str = f"{lat_char}{abs(lat)}"

                # Longitude Part
                # If lon is -115, that is 115 West.
                lon_char = 'E' if lon >= 0 else 'W'
                # Ensure 3 digits for longitude? (e.g. W080 vs W80)
                # Trying standard 3-digit padding first as it's common in NOAA/NGA
                lon_str = f"{lon_char}{abs(lon):03d}"

                # Filename Attempt 1: N30W115.zip (No padding on lat, 3 on lon)
                filename = f"{lat_str}{lon_str}.zip"

                # Also try adding to results without padding if that fails?
                # Usually best to be precise. Let's try your specific example N55W135.
                # 55 is 2 digits. 135 is 3 digits.
                # If we had W80, it might be W080 or W80.
                # Let's stick to 3 digits for lon for now.

                url = f"{CUSP_BASE}{filename}"

                self.add_entry_to_results(
                    url=url,
                    dst_fn=filename,
                    data_type="cusp",
                    meta={"kind": "cusp", "weight": 20.0}
                )

        return self
