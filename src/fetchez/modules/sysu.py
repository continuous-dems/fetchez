#!/usr/bin/env python

"""
fetchez.modules.sysu
~~~~~~~~~~~~~~~~~~~~~~
Fetches the SYSU_topo netcdf
SYSU_Topo: a 1-arc-minute global bathymetry from SWOT-derived gravity using the gravity-geological method.

https://www.nature.com/articles/s41597-026-06641-5
https://zenodo.org/records/17958545

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez import cli
from fetchez.core import CUDEM_USER_AGENT
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


DOWNLOAD_URL = "https://zenodo.org/records/17958545/files/SYSU_Topo_v1.0.nc"


HEADERS = {
    # "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "User-Agent": CUDEM_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "referer": "https://zenodo.org/records/17958545/",
}


@cli.cli_opts(
    help_text="Fetch SYSU_topo global bathymetry (Open Access).",
    product="Product ID. Currently only 'SYSU_topo' is supported.",
)
class Seanoe(FetchModule):
    name = "sysu"
    meta_category = "Bathymetry"
    meta_desc = "SYSU Global Gravity-Geological Bathymetry"
    meta_agency = "SYSU"
    meta_tags = ["bathymetry", "gravity", "global", "open-science"]
    meta_region = "Global"
    meta_resolution = "1 arc-minute (~2km)"
    meta_license = "Creative Commons Attribution 4.0 International"
    meta_urls = {
        "home": "https://zenodo.org/records/17958545",
        "doi": "https://doi.org/10.5281/zenodo.17958544",
    }

    FILENAME = "SYSU_Topo_v1.0.nc"

    def __init__(self, product="SYSU_topo", **kwargs):
        super().__init__(name="sysu", **kwargs)
        self.headers = HEADERS

    def run(self):
        self.add_entry_to_results(
            url=DOWNLOAD_URL,
            dst_fn=self.FILENAME,
            data_type="netcdf",
            # layers=[""],
        )
