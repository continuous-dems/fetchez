#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.seanoe
~~~~~~~~~~~~~~~~~~~~~~~~~~
Fetches FES2014 Derived Surfaces (LAT/MSL) from SEANOE.
DOI: 10.17882/85408
"""

import logging
from fetchez import core, cli

logger = logging.getLogger(__name__)


DOWNLOAD_URL = "https://www.seanoe.org/data/00742/85408/data/90469.nc"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "referer": "https://www.seanoe.org/data/00742/85408/",
}


@cli.cli_opts(
    help_text="Fetch FES2014 Global Tide Surfaces from SEANOE (Open Access).",
    product="Product ID. Currently only 'fes2014_derived' is supported.",
)
class Seanoe(core.FetchModule):
    FILENAME = "FES2014_LAT_MSL_global.nc"

    def __init__(self, product="fes2014_derived", **kwargs):
        super().__init__(name="seanoe", **kwargs)
        self.headers = HEADERS

    def run(self):
        self.add_entry_to_results(
            url=DOWNLOAD_URL,
            dst_fn=self.FILENAME,
            data_type="netcdf",
            layers=["LAT", "MSL"],
        )
