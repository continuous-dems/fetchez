#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.globathy
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch GLOBathy (Global Lake Bathymetry) data.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from fetchez import core
from fetchez import cli

# Figshare download link for GLOBathy basic parameters (CSV/Shapefile)
GLOBATHY_URL = 'https://springernature.figshare.com/ndownloader/files/28919991'

# =============================================================================
# GLOBathy Module
# =============================================================================
@cli.cli_opts(
    help_text="GLOBathy Global Lake Bathymetry"
)
class GLOBathy(core.FetchModule):
    """Fetch GLOBathy (Global Lakes Bathymetry).

    GLOBathy provides bathymetric estimates (depth, volume) for the 1.4 million
    lakes in HydroLAKES. It uses the same 'Hylak_id' identifier, allowing
    easy joining with the HydroLAKES polygons.

    **Note:** This module downloads the global parameter dataset (~250MB).

    References:
      - https://figshare.com/articles/dataset/GLOBathy_Bathymetric_Data/13353392
    """

    def __init__(self, **kwargs):
        super().__init__(name='globathy', **kwargs)


    def run(self):
        """Run the GLOBathy fetching logic."""

        self.add_entry_to_results(
            url=GLOBATHY_URL,
            dst_fn='GLOBathy_basic_parameters.zip',
            data_type='table',
            agency='Khazaei et al.',
            title='GLOBathy Parameters'
        )

        return self
