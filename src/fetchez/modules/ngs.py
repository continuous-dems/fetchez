#!/usr/bin/env python

"""
fetchez.modules.ngs
~~~~~~~~~~~~~~~~~~~

Fetch National Geodetic Survey (NGS) Monuments (Survey Marks) from NOAA.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode

from fetchez import cli
from fetchez.modules import FetchModule

NGS_SEARCH_URL = "https://geodesy.noaa.gov/api/nde/bounds?"


# =============================================================================
# NGS Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA NGS Survey Monuments",
    datum="Preferred Datum for metadata (e.g., 'orthoHt', 'geoidHt'). Note: API fetches all available data.",
)
class NGS(FetchModule):
    name = "ngs"
    meta_category = "Geodesy"
    meta_desc = "National Geodetic Survey (NGS) Monuments"
    meta_agency = "NOAA"
    meta_tags = ["ngs", "monuments", "survey", "benchmarks", "geodesy", "control"]
    meta_region = "USA"
    meta_resolution = "Point Data"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://geodesy.noaa.gov/"}

    """Fetch NGS Survey Monuments (Datasheets).

    The National Geodetic Survey (NGS) provides information about survey marks
    (bench marks) including precise latitude, longitude, and elevation.

    This module queries the NGS Data Explorer API to find all monuments
    within the requested bounding box.

    References:
      - https://geodesy.noaa.gov/
    """

    def __init__(self, datum: str = "geoidHt", **kwargs):
        super().__init__(name="ngs", **kwargs)
        self.datum = datum

    def run(self):
        """Run the NGS fetching logic."""

        if self.wgs_region is None:
            return []

        w, e, s, n = self.wgs_region

        params = {"minlon": w, "maxlon": e, "minlat": s, "maxlat": n}

        full_url = f"{NGS_SEARCH_URL}{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        out_fn = f"ngs_monuments_{r_str}.json"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="json",
            agency="NOAA NGS",
            title="NGS Survey Monuments",
        )

        return self
