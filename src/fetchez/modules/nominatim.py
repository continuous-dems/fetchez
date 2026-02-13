#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.nominatim
~~~~~~~~~~~~~

This module queries nominatim for coordinates of places.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez import core
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

NOMINATUM_URL = "https://nominatim.openstreetmap.org/search"


@cli.cli_opts(help_text="Nominatum place queries", query="Query String")
class Nominatim(core.FetchModule):
    """Fetch coordinates from OpenStreetMap's Nominatim service."""

    def __init__(self, query="boulder", **kwargs):
        super().__init__(name="nominatim", **kwargs)
        self.query = query

        ## Nominatim usage policy requires a custom User-Agent and Referer.
        self.headers = {
            "User-Agent": "CUDEM/Fetches 1.0 (cudem.colorado.edu)",
            "Referer": "https://cudem.colorado.edu",
        }

    def run(self):
        if utils.str_or(self.query) is not None:
            ## Construct parameters using the module's urlencode helper
            params = {
                "q": self.query,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
            }
            query_str = core.urlencode(params)
            q_url = f"{NOMINATUM_URL}?{query_str}"

            _req = core.Fetch(q_url, headers=self.headers).fetch_req()

            if _req is not None and _req.status_code == 200:
                try:
                    results = _req.json()
                    if results and isinstance(results, list) and len(results) > 0:
                        ## Parse coordinates
                        x = utils.float_or(results[0].get("lon"))
                        y = utils.float_or(results[0].get("lat"))

                        ## Print the display name found (helpful for debugging vague queries)
                        disp_name = results[0].get("display_name", "Unknown Location")
                        logger.info(f"Resolved '{self.query}' to: {disp_name}")

                        # Standard output for CLI piping: "lon, lat"
                        # print(f'{x}, {y}')

                        self.add_entry_to_results(
                            url=q_url,
                            dst_fn=None,
                            data_type="coords",
                            metadata=results[0],
                            x=x,
                            y=y,
                        )
                        # self.results.append({
                        #     'url': q_url,
                        #     'dst_fn': None,
                        #     'data_type': 'coords',
                        #     'metadata': results[0],
                        #     'x': x,
                        #     'y': y
                        # })
                    else:
                        logger.warning(
                            f"Nominatim: No results found for query '{self.query}'"
                        )
                except Exception as e:
                    logger.error(f"Nominatim parse error")
            else:
                status = _req.status_code if _req else "Connection Failed"
                logger.error(f"Nominatim request failed: {status}")
