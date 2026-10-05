#!/usr/bin/env python

"""
fetchez.modules.seanoe
~~~~~~~~~~~~~~~~~~~~~~
Fetches FES2014 Derived Surfaces (LAT/MSL) from SEANOE.
DOI: 10.17882/85408
"""

import logging

from fetchez import cli
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


DOWNLOAD_URL = "https://www.seanoe.org/data/00742/85408/data/90469.nc"
TIDAL_DATUMS_URL = "https://www.seanoe.org/data/01005/111620/data/125657.csv"


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
class Seanoe(FetchModule):
    name = "seanoe"
    meta_category = "Geodesy"
    meta_desc = "FES Global Gravity, Altimetry, and Tide Models"
    meta_agency = "SHOM"
    meta_tags = ["tides", "lat", "msl", "fes2014", "global", "open-science"]
    meta_region = "Global"
    meta_resolution = "1 arc-minute (~2km)"
    meta_license = "Public / Scientific Use"
    meta_urls = {"home": "https://www.seanoe.org/data/00742/85408/"}

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
