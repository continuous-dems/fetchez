#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.sun_moon
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Sun/Moon Rise/Set times and phases from the US Naval Observatory (USNO).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli
from fetchez import utils

USNO_API = "https://aa.usno.navy.mil/api/rstt/oneday"

@cli.cli_opts(
    help_text="USNO Sun/Moon Ephemeris",
    date="Date (YYYY-MM-DD). Default: Today.",
    timezone="Timezone offset (e.g. -7 for MST). Default: 0 (UTC)."
)
class SunMoon(core.FetchModule):
    """Fetch official Sun/Moon data for the center of the region.
    
    Returns a JSON file containing:
    - Begin/End of Civil Twilight
    - Sunrise/Sunset
    - Moonrise/Moonset
    - Moon Phase
    """

    def __init__(self, date=None, timezone=0, **kwargs):
        super().__init__(name="sun_moon", **kwargs)
        self.date = date if date else utils.today_str() 
        self.timezone = timezone

    def run(self):
        if self.region is None:
            return []

        # Calculate Centroid of the Region
        w, e, s, n = self.region
        center_lon = (w + e) / 2
        center_lat = (s + n) / 2

        params = {
            "date": self.date,
            "coords": f"{center_lat},{center_lon}",
            "tz": self.timezone
        }

        full_url = f"{USNO_API}?{urlencode(params)}"
        
        out_fn = f"ephemeris_{self.date}_{center_lat:.2f}_{center_lon:.2f}.json"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="json",
            agency="US Naval Observatory",
            title=f"Sun/Moon Data {self.date}"
        )

        return self
