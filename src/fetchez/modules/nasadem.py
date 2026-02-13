#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.nasadem
~~~~~~~~~~~~~~~~~~~~~~~

Fetch NASA Digital Elevation Model (NASADEM) data via OpenTopography.

:copyright: (c) 2020 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import math
from fetchez import core
from fetchez import cli

# OpenTopography S3 Mirror (Public)
NASADEM_BASE_URL = 'https://opentopography.s3.sdsc.edu/minio/download/raster/NASADEM/NASADEM_be'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'referer': NASADEM_BASE_URL
}

# =============================================================================
# NASADEM Module
# =============================================================================
@cli.cli_opts(
    help_text="NASA Digital Elevation Model (NASADEM)"
)
class NASADEM(core.FetchModule):
    """Fetch NASADEM Global Elevation data.

    NASADEM is a modernization of the SRTM data, featuring improved
    height accuracy and void filling. The data is distributed in
    1x1 degree tiles (SRTM HGT format) at 1 arc-second (~30m) resolution.

    This module mathematically generates tile URLs for the requested region,
    avoiding the need to query a catalog server.

    References:
      - https://www.earthdata.nasa.gov/esds/competitive-programs/measures/nasadem
      - https://opentopography.org/
    """

    def __init__(self, **kwargs):
        super().__init__(name='nasadem', **kwargs)
        self.headers = HEADERS


    def _format_tile_name(self, lat, lon):
        """Generate NASADEM filename from lat/lon integers.
        Format: NASADEM_HGT_nXXeYYY.hgt
        """

        # Latitude: n/s + 2 digits
        ns = 'n' if lat >= 0 else 's'
        lat_str = f"{abs(lat):02d}"

        # Longitude: e/w + 3 digits
        ew = 'e' if lon >= 0 else 'w'
        lon_str = f"{abs(lon):03d}"

        return f"NASADEM_HGT_{ns}{lat_str}{ew}{lon_str}.tif"


    def run(self):
        """Run the NASADEM fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        # We need every 1x1 degree tile that touches the region.
        # Floor the mins, Ceil the maxes.
        x_min = int(math.floor(w))
        x_max = int(math.ceil(e))
        y_min = int(math.floor(s))
        y_max = int(math.ceil(n))

        for x in range(x_min, x_max):
            for y in range(y_min, y_max):

                # Note: SRTM/NASADEM tiles are named by their lower-left corner.
                fname = self._format_tile_name(y, x)

                # Construct URL
                url = f"{NASADEM_BASE_URL}/{fname}?token="

                # Add to results
                self.add_entry_to_results(
                    url=url,
                    dst_fn=fname,
                    data_type='gtif',
                    agency='NASA / OpenTopography',
                    title=f"NASADEM Tile {y}/{x}"
                )

        return self
