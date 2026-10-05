#!/usr/bin/env python

"""
fetchez.modules.d2c
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Distance to Coast dataset from NASA OBPG
"""

import logging
import urllib.parse

from fetchez.modules.base import FetchModule

logger = logging.getLogger(__name__)

OBPG_BASE_URL = "https://pae-paha.pacioos.hawaii.edu/thredds/ncss/grid/"


class Dist2Coast(FetchModule):
    """Fetches NASA OBPG distance-to-coast raster data from PacIOOS THREDDS."""

    name = "dist2coast"
    meta_category = "Reference"
    meta_desc = "Global Distance to Nearest Coastline (0.01-Degree Grid)."
    meta_agency = "NASA OBPG / PacIOOS"
    meta_resolution = "1 degree"
    meta_license = "Public Domain"
    meta_tags = ["distance", "coast", "ocean", "land", "raster", "reference"]

    def __init__(self, variant="base", **kwargs):
        super().__init__(name="dist2coast", **kwargs)

        # Valid variants: 'base', 'ocean', 'land'
        self.variant = str(variant).lower()
        self.dataset_map = {
            "base": "dist2coast_1deg",  # +/- continuous gradient
            "ocean": "dist2coast_1deg_ocean",  # Water only
            "land": "dist2coast_1deg_land",  # Land only
        }

        if self.variant not in self.dataset_map:
            logger.warning(
                f"[{self.name}] Unknown variant '{self.variant}'. Defaulting to 'base'."
            )
            self.variant = "base"

    def run(self):
        if not self.wgs_region:
            logger.error(f"[{self.name}] Requires a bounding box region to run.")
            return

        w, e, s, n = self.wgs_region
        dataset_id = self.dataset_map[self.variant]

        variant_url = f"{OBPG_BASE_URL}{dataset_id}"
        params = {
            "var": "dist",
            "north": str(n),
            "south": str(s),
            "east": str(e),
            "west": str(w),
            "addLatLon": "true",
            "accept": "netcdf",
        }

        query = urllib.parse.urlencode(params)
        url = f"{variant_url}?{query}"

        out_name = f"dist2coast_{self.variant}_{w}_{s}_{e}_{n}.nc"

        logger.info(f"[{self.name}] Querying PacIOOS for D2C '{self.variant}' grid...")
        self.add_entry_to_results(
            url,
            out_name,
            "netcdf",
            title=f"NASA OBPG Distance to Coast ({self.variant.capitalize()})",
        )

        return self
