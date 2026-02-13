#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.srtmplus
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch SRTM15+ Global Bathymetry and Topography from Scripps Institution of Oceanography (UCSD).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

SRTM_PLUS_CGI_URL = 'https://topex.ucsd.edu/cgi-bin/get_srtm15.cgi'

# =============================================================================
# SRTM Plus Module
# =============================================================================
@cli.cli_opts(
    help_text="SRTM15+ Global Bathymetry/Topography (Scripps/UCSD)"
)

class SRTMPlus(core.FetchModule):
    """Fetch SRTM15+ Global Bathymetry and Topography.

    Data is sourced from the Scripps Institution of Oceanography (UCSD).
    This dataset merges SRTM land topography with gravity-derived bathymetry
    at a resolution of 15 arc-seconds (~500m).

    The module queries the CGI interface to generate an XYZ text file
    for the specific requested bounding box.

    References:
      - https://topex.ucsd.edu/WWW_html/srtm15_plus.html
    """

    def __init__(self, **kwargs):
        super().__init__(name='srtm_plus', **kwargs)


    def run(self):
        """Run the SRTM+ fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        data = {
            'north': n,
            'west': w,
            'south': s,
            'east': e,
        }

        full_url = f"{SRTM_PLUS_CGI_URL}?{urlencode(data)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace('.', 'p').replace('-', 'm')
        out_fn = f"srtm_{r_str}.xyz"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type='xyz',
            agency='SIO / UCSD',
            title='SRTM15+ Global Bathy/Topo'
        )

        return self
