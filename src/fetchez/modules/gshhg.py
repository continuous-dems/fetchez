#!/usr/bin/env python

"""
fetchez.modules.gshhg
~~~~~~~~~~~~~~~~~~~~~

Fetch GSHHG (Global Self-consistent, Hierarchical, High-resolution Geography) data.
Provides global coastline polygons for international masking and inland decay.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez import cli
from fetchez.modules.base import FetchModule

logger = logging.getLogger(__name__)

# Standard NCEI distribution for the Shapefile version
GSHHG_NOAA_URL = (
    "https://www.ngdc.noaa.gov/mgg/shorelines/data/gshhg/latest/gshhg-shp-2.3.7.zip"
)
GSHHG_SHP_URL = "http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip"
GSHHG_GMT_URL = "http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-gmt-2.3.7.tar.gz"


@cli.cli_opts(
    help_text="Global Self-consistent, Hierarchical, High-resolution Geography (GSHHG)",
    resolution="Resolution to use: f (full), h (high), i (inter), l (low), c (crude). Default: h",
)
class GSHHG(FetchModule):
    name = "gshhg"
    meta_category = "Reference"
    meta_desc = "Global Self-consistent, Hierarchical, High-resolution Geography"
    meta_agency = "NOAA NCEI / SOEST"
    meta_tags = ["shoreline", "coastline", "gshhg", "global", "vector"]
    meta_resolution = "Global (Multiple Resolutions)"
    meta_license = "Public Domain (LGPL)"
    meta_urls = {"home": "https://www.soest.hawaii.edu/pwessel/gshhg/index.html"}

    def __init__(self, resolution="h", **kwargs):
        super().__init__(**kwargs)

        self.resolution = resolution.lower()
        if self.resolution not in ["f", "h", "i", "l", "c"]:
            logger.warning(
                f"Invalid GSHHG resolution '{self.resolution}'. Defaulting to 'h'."
            )
            self.resolution = "h"

        self.data_type = "vector"
        self.format = "zip"

    def run(self):
        """Fetch the global GSHHG shapefile bundle."""

        filename = "gshhg-shp-latest.zip"

        logger.info("Adding Global GSHHG Shoreline archive to fetch queue...")

        # Target the specific shapefile inside the ZIP (L1 = Ocean/Land boundary)
        # target_shp = f"GSHHS_shp/{self.resolution}/GSHHS_{self.resolution}_L1.shp"
        target_shp = f"GSHHS_{self.resolution}_L1"

        self.add_entry_to_results(
            url=GSHHG_SHP_URL,
            dst_fn=filename,
            data_type=target_shp,
            weight=50.0,
        )
        return self
