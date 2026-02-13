#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.vgg
~~~~~~~~~~~~~~~~~~~

Fetch Vertical Gravity Gradient (VGG) data from Scripps Institution of Oceanography.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from fetchez import core
from fetchez import cli

# =============================================================================
# Constants
# =============================================================================
# VGG is often stored as 'curv' (curvature) in the SIO archives.
# Version 33.1 is the latest stable release as of 2026.
VGG_URL = "https://topex.ucsd.edu/pub/global_grav_1min/curv_33.1.nc"


# =============================================================================
# VGG Module
# =============================================================================
@cli.cli_opts(help_text="Vertical Gravity Gradient (Scripps/UCSD)")
class VGG(core.FetchModule):
    """
    Fetch the Vertical Gravity Gradient (VGG) global grid.

    The VGG (often labeled as 'curvature') is the second vertical derivative
    of the geopotential. It highlights high-frequency features like seamounts,
    fracture zones, and abyssal hill fabric that are often smoothed out in
    standard gravity anomaly maps.

    **Note:** This module downloads the full global grid (~640 MB).

    References:
      - https://topex.ucsd.edu/WWW_html/mar_grav.html
      - https://topex.ucsd.edu/sandwell/publications/154_Science_gravity.pdf
    """

    def __init__(self, **kwargs):
        super().__init__(name="vgg", **kwargs)

    def run(self):
        """Run the VGG fetching logic."""

        # Download the global NetCDF
        self.add_entry_to_results(
            url=VGG_URL,
            dst_fn="curv_33.1.nc",
            data_type="netcdf",
            agency="SIO / UCSD",
            title="Global Vertical Gravity Gradient (VGG)",
        )

        return self
