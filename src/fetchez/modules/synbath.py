#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.synbath
~~~~~~~~~~~~~~~~~~~~~~~

Fetch UCSD SynBath Global Synthetic Bathymetry.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from fetchez import core
from fetchez import cli

# The latest stable release (V2.0)
SYNBATH_URL = "https://topex.ucsd.edu/pub/synbath/SYNBATH_V2.0.nc"


# =============================================================================
# SynBath Module
# =============================================================================
@cli.cli_opts(
    help_text="UCSD SynBath Global Bathymetry (Geologically Constrained)",
)
class SynBath(core.FetchModule):
    """Fetch the UCSD SynBath (Synthetic Bathymetry) dataset.

    SynBath is a global bathymetry grid that merges satellite gravity with
    geological models (seafloor age, spreading rate, sediment thickness) to
    create realistic "synthetic" textures for unmapped abyssal hills and
    seamounts.

    **Note:** This module downloads the full global grid (~6.2 GB).
    There is currently no regional subsetting service available for SynBath.

    References:
      - https://topex.ucsd.edu/pub/synbath/SYNBATH_publication.pdf
    """

    def __init__(self, **kwargs):
        super().__init__(name="synbath", **kwargs)

    def run(self):
        """Run the SynBath fetching logic."""

        # We always fetch the full file.
        self.add_entry_to_results(
            url=SYNBATH_URL,
            dst_fn="SYNBATH_V2.0.nc",
            data_type="netcdf",
            agency="SIO / UCSD",
            title="SynBath Global V2.0",
        )

        return self
