#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.chs
~~~~~~~~~~~~~~~~~~~~

Fetch Canadian Hydrographic Service (CHS) NONNA data via WCS.

The NONNA (Non-Navigational) bathymetry data is available at
10m and 100m resolutions via the CHS GeoServer.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from urllib.parse import urlencode

from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

CHS_WCS_URL = "https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs"


# =============================================================================
# CHS Module
# =============================================================================
@cli.cli_opts(
    help_text="Canadian Hydrographic Service (NONNA Bathymetry)",
    resolution="Data resolution in meters: '10' or '100' (Default: 100)",
)
class CHS(core.FetchModule):
    """Fetch bathymetric soundings from the CHS via Web Coverage Service (WCS).

    Supports NONNA-10 (10m resolution) and NONNA-100 (100m resolution).
    The module constructs a WCS GetCoverage request for the input region.
    """

    def __init__(self, resolution: str = "100", **kwargs):
        super().__init__(name="chs", **kwargs)

        self.resolution = str(resolution)
        if self.resolution not in ["10", "100"]:
            logger.warning(
                f"Invalid CHS resolution '{self.resolution}'. Defaulting to '100'."
            )
            self.resolution = "100"

    def run(self):
        """Run the CHS fetching module."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        # Construct WCS 2.0 GetCoverage Parameters
        # Note: CHS GeoServer uses 'Lat' and 'Long' axis labels for subsetting.
        coverage_id = f"nonna__NONNA {self.resolution} Coverage"

        params = {
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "CoverageID": coverage_id,
            "subset": [f"Long({w},{e})", f"Lat({s},{n})"],
            "subsettingcrs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "outputcrs": "http://www.opengis.net/def/crs/EPSG/0/4326",
            "format": "image/tiff",
        }

        query_string = urlencode(params, doseq=True)
        full_url = f"{CHS_WCS_URL}?{query_string}"

        region_tag = f"{w:.4f}_{s:.4f}"
        out_fn = f"chs_nonna_{self.resolution}m_{region_tag}.tif"

        logger.info(f"Generated WCS request for CHS NONNA-{self.resolution}...")

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="chs_wcs_gtif",
            agency="CHS",
            title=f"NONNA {self.resolution}m Bathymetry",
            license="Open Government Licence - Canada",
        )

        return self
