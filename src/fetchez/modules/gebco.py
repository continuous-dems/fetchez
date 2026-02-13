#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.gebco
~~~~~~~~~~~~~~~~~~~~~

Fetch General Bathymetric Chart of the Oceans (GEBCO) data.
Supports regional subsetting via Cloud Optimized GeoTIFF (COG)
or full global downloads from BODC.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez.core import FetchModule

logger = logging.getLogger(__name__)

# =============================================================================
# Data Sources
# =============================================================================

# BODC / Official GEBCO - Global Zipped Downloads
GEBCO_GLOBAL_URLS = {
    'grid': 'https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024/geotiff/',
    'tid': 'https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024_tid/geotiff/',
    'sub_ice': 'https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024_sub_ice_topo/geotiff/'
}

class GEBCO(FetchModule):
    """Fetch GEBCO global bathymetry data.

    GEBCO provides a global terrain model at ~15 arc-seconds (~500m).

    Layers:
      - grid: Standard bathymetry/topography (Ice Surface). Default.
      - sub_ice: Bedrock elevation (Ice removed).
      - tid: Type Identifier (Source of data per pixel).

    Examples:
      fetchez gebco -R -90/-89/25/26
      fetchez gebco --layer tid -R ...
      fetchez gebco --layer sub_ice
    """

    def __init__(self, layer='grid', **kwargs):
        """
        Args:
            layer (str): 'grid', 'tid', or 'sub_ice'.
            global_grid (bool): Legacy flag, forces source='global'.
        """

        super().__init__(name='gebco', **kwargs)

        self.layer = layer.lower()

        if self.layer not in GEBCO_GLOBAL_URLS:
            valid = ", ".join(GEBCO_GLOBAL_URLS.keys())
            logger.warning(f"Unknown GEBCO layer '{self.layer}'. Defaulting to 'grid'. Valid: {valid}")
            self.layer = 'grid'


    def run(self):
        """Setup for Official Global Download."""

        url = GEBCO_GLOBAL_URLS.get(self.layer)
        if not url:
            logger.error(f"No Global URL available for layer '{self.layer}'.")
            return

        dst_fn = f"gebco_2024_{self.layer}_global.zip"
        self.add_entry_to_results(
            url=url,
            dst_fn=dst_fn,
            data_type="archive",
        )
