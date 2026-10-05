#!/usr/bin/env python

"""
fetchez.modules.ipinfo
~~~~~~~~~~~~~~~~~~~~~~

A fun module to fetch IP geolocation data from ipinfo.io.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez import cli
from fetchez.core import Fetch
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Fetch IP Geolocation Data from ipinfo.io",
    ip="Specific IP address to lookup (default: current IP)",
)
class IPInfo(FetchModule):
    name = "ipinfo"
    meta_category = "Reference"
    meta_desc = "Query IP Addresses for coordinates"
    meta_agency = "IPinfo"
    meta_tags = ["utility", "geolocation", "ip", "context"]
    meta_region = "Custom"
    meta_resolution = "N/A"
    meta_license = "CC BY-SA 4.0 (attribution required)"
    meta_urls = {"home": "https://ipinfo.io/"}

    """Fetch JSON data from ipinfo.io.

    If no IP is provided, it fetches data for the machine running the script.
    """

    def __init__(self, ip=None, **kwargs):
        # We set a default name 'ipinfo' for the output directory
        super().__init__(name="ipinfo", **kwargs)
        self.ip = ip

    def run(self):
        """Build the URL and add it to the results list."""

        if self.ip:
            url = f"https://ipinfo.io/{self.ip}/json"
            dst_fn = f"{self.ip}.json"
        else:
            url = "https://ipinfo.io/json"
            dst_fn = "my_ip.json"

        req = Fetch(url).fetch_req()
        if req is not None and req.status_code == 200:
            try:
                results = req.json()
                if results and isinstance(results, dict):
                    ## Parse coordinates
                    loc = [float(x) for x in results.get("loc").split(",")]
                    y, x = loc

                    self.add_entry_to_results(
                        url=url,
                        dst_fn=dst_fn,
                        data_type="json",
                        metadata=results,
                        x=x,
                        y=y,
                        provider="ipinfo.io",
                    )
                else:
                    logger.warning(f"IPInfo: No results found for query '{self.query}'")
            except Exception as e:
                logger.error(f"IPInfo parse error: {e}")
