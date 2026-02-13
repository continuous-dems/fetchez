#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.emodnet
~~~~~~~~~~~~~~~~~~~~~~~

Fetch European elevation data from EMODnet Bathymetry.
Supports retrieval via WCS (default) or ERDDAP.

:copyright: (c) 2021 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

EMODNET_WCS_URL = 'https://ows.emodnet-bathymetry.eu/wcs?'
EMODNET_ERDDAP_BASE = 'https://erddap.emodnet.eu/erddap/griddap/dtm_2020_v2_e0bf_e7e4_5b8f'

RES_115M = 0.00104166666666667

# =============================================================================
# EMODNet Module
# =============================================================================
@cli.cli_opts(
    help_text="EMODnet Bathymetry (Europe)",
    want_erddap="Use ERDDAP source instead of WCS",
    erddap_format="Format for ERDDAP download (nc, asc, csv, etc.) [Default: nc]",
    layer="Data Layer: 'mean' (Depth), 'std' (Error), 'source' (Source ID), 'quality'",
    resolution="Override WCS resolution (in degrees). Default is ~0.001 (115m)."
)

class EMODNet(core.FetchModule):
    """Fetch Digital Terrain Model data from EMODnet Bathymetry.

    EMODnet Bathymetry provides a high-resolution bathymetry for European sea basins.

    Supported Layers:
      - mean    : Average depth (Best for general use)
      - std     : Standard deviation (Uncertainty)
      - source  : Source Identifier (Which survey did this pixel come from?)
      - quality : Quality Index

    References:
      - Portal: https://portal.emodnet-bathymetry.eu/
    """

    def __init__(self,
                 want_erddap: bool = False,
                 erddap_format: str = 'nc',
                 layer: str = 'mean',
                 resolution: float = None,
                 **kwargs):
        super().__init__(name='emodnet', **kwargs)
        self.want_erddap = want_erddap
        self.erddap_format = erddap_format
        self.layer = layer.lower()
        self.resolution = float(resolution) if resolution else RES_115M


    def run(self):
        """Run the EMODnet fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        layer_map = {
            'mean':   ('emodnet:mean', 'elevation'),
            'depth':  ('emodnet:mean', 'elevation'),
            'std':    ('emodnet:stdev', 'standard_deviation'),
            'error':  ('emodnet:stdev', 'standard_deviation'),
            'source': ('emodnet:source', 'source_id'),
            'id':     ('emodnet:source', 'source_id'),
            'quality':('emodnet:qa', 'quality_index')
        }

        wcs_cov, erddap_var = layer_map.get(self.layer, ('emodnet:mean', 'elevation'))

        if self.want_erddap:
            query = f"{erddap_var}[({s}):1:({n})][({w}):1:({e})]"

            erddap_url = f"{EMODNET_ERDDAP_BASE}.{self.erddap_format}?{query}"

            r_str = f"w{w}_e{e}_s{s}_n{n}".replace('.', 'p').replace('-', 'm')
            # Include layer name in filename so they don't overwrite each other
            out_fn = f"emodnet_{self.layer}_{r_str}.{self.erddap_format}"

            self.add_entry_to_results(
                url=erddap_url,
                dst_fn=out_fn,
                data_type=self.erddap_format,
                agency='EMODnet',
                title=f'EMODnet DTM {self.layer.title()} (ERDDAP)'
            )

        else:
            bbox_str = f"{w},{s},{e},{n}"

            wcs_params = {
                'service': 'WCS',
                'request': 'GetCoverage',
                'version': '1.0.0',
                'coverage': wcs_cov,
                'crs': 'EPSG:4326',
                'bbox': bbox_str,
                'format': 'GeoTIFF',
                'resx': self.resolution,
                'resy': self.resolution,
            }

            full_url = f"{EMODNET_WCS_URL}{urlencode(wcs_params)}"

            r_str = f"w{w}_e{e}_s{s}_n{n}".replace('.', 'p').replace('-', 'm')
            out_fn = f"emodnet_{self.layer}_{r_str}.tif"

            self.add_entry_to_results(
                url=full_url,
                dst_fn=out_fn,
                data_type='emodnet_wcs',
                agency='EMODnet',
                title=f'EMODnet DTM {self.layer.title()}'
            )

        return self
