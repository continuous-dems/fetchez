#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.hydrolakes
~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch HydroLAKES Global Lake Polygons.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from fetchez import core
from fetchez import cli

HYDROLAKES_SHP_URL = (
    "https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip"
)
HYDROLAKES_GDB_URL = (
    "https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_gdb.zip"
)


# =============================================================================
# HydroLAKES Module
# =============================================================================
@cli.cli_opts(
    help_text="HydroLAKES Global Polygons",
    format="File format: 'shp' (Shapefile) or 'gdb' (GeoDatabase). Default: shp",
)
class HydroLAKES(core.FetchModule):
    """Fetch HydroLAKES global shoreline polygons.

    HydroLAKES provides the shoreline polygons for all global lakes
    with a surface area of at least 10 hectares (1.4 million lakes).

    **Note:** This module downloads the full global dataset (~300MB - 1GB).

    References:
      - https://www.hydrosheds.org/products/hydrolakes
    """

    def __init__(self, format: str = "shp", **kwargs):
        super().__init__(name="hydrolakes", **kwargs)
        self.format = format.lower()

    def run(self):
        """Run the HydroLAKES fetching logic."""

        if self.format == "gdb":
            url = HYDROLAKES_GDB_URL
            ext = "gdb.zip"
        else:
            url = HYDROLAKES_SHP_URL
            ext = "shp.zip"

        self.add_entry_to_results(
            url=url,
            dst_fn=f"HydroLAKES_polys_v10_{self.format}.{ext}",
            data_type="vector",
            agency="HydroSHEDS",
            title=f"HydroLAKES v1.0 ({self.format.upper()})",
        )

        return self
