#!/usr/bin/env python

"""
fetchez.modules.wikigeo
~~~~~~~~~~~~~~~~~~~~~~~

Fetch Wikipedia articles located within a region.
Useful for building context, labeling maps, or identifying features.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode

from fetchez import cli, spatial
from fetchez.modules import FetchModule

WIKI_API = "https://en.wikipedia.org/w/api.php"


@cli.cli_opts(
    help_text="Wikipedia Geosearch",
    limit="Max results per chunk (default 500, max 500)",
    chunk_size="Size of search chunks in degrees (default 0.1 to satisfy API limits)",
)
class WikiGeo(FetchModule):
    name = "wikigeo"
    meta_category = "Context"
    meta_desc = "Geolocated Wikipedia Articles (Points of Interest)"
    meta_agency = "Wikipedia Foundation"
    meta_tags = ["wikipedia", "context", "labels", "history", "poi", "geosearch"]
    meta_region = "Global"
    meta_resolution = "Point Data"
    meta_license = "CC-BY-SA 3.0"
    meta_urls = {
        "home": "https://www.wikipedia.org/",
        "api": "https://en.wikipedia.org/w/api.php",
    }

    """Fetch geolocated Wikipedia articles.

    The Wikipedia API limits geosearch to small areas. This module automatically
    chunks your region into small tiles (0.1 degree default) to ensure
    coverage.

    Output is JSON. Use a post-hook to convert to GeoJSON/Shapefile.
    """

    def __init__(self, limit=500, chunk_size=0.1, **kwargs):
        super().__init__(name="wikigeo", **kwargs)
        self.limit = limit
        self.chunk_size = float(chunk_size)

    def run(self):
        if self.wgs_region is None:
            return []

        # Wikipedia 'gsbbox' requires: top|left|bottom|right (North|West|South|East)
        # Chunk the region because Wiki API fails on large bboxes
        chunks = spatial.chunk_region(self.wgs_region, self.chunk_size)

        for chunk in chunks:
            w, e, s, n = chunk

            # Format for API: Top|Left|Bottom|Right -> N|W|S|E
            gsbbox = f"{n}|{w}|{s}|{e}"

            params = {
                "action": "query",
                "list": "geosearch",
                "gsbbox": gsbbox,
                "gslimit": self.limit,
                "gsprimary": "all",  # Include primary and secondary coordinates
                "format": "json",
            }

            full_url = f"{WIKI_API}?{urlencode(params)}"

            r_str = f"w{w:.3f}_n{n:.3f}".replace(".", "p").replace("-", "m")
            out_fn = f"wiki_context_{r_str}.json"

            self.add_entry_to_results(
                url=full_url,
                dst_fn=out_fn,
                data_type="json",
                agency="Wikipedia",
                title=f"Wiki GeoSearch {r_str}",
            )

        return self
