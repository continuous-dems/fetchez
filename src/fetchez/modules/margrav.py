#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.margrav
~~~~~~~~~~~~~~~~~~~~~~~

Fetch Marine Gravity data from Scripps Institution of Oceanography (UCSD).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

MARGRAV_CGI_URL = "https://topex.ucsd.edu/cgi-bin/get_data.cgi"
# Note: This points to the global predicted topography grid derived from gravity
MARGRAV_IMG_URL = "https://topex.ucsd.edu/pub/global_topo_1min/topo_27.1.img"
MARGRAV_GLOBAL_NC = "https://topex.ucsd.edu/pub/global_grav_1min/grav_33.1.nc"


# =============================================================================
# MarGrav Module
# =============================================================================
@cli.cli_opts(
    help_text="Marine Gravity (Scripps/UCSD)",
    mag="Magnitude/Zoom level (0.0-1.0). Default: 1.0 (Full Res)",
    global_grid="Fetch the full global grid (IMG format) instead of a regional slice.",
)
class MarGrav(core.FetchModule):
    """Fetch Marine Gravity Satellite Altimetry Topography.

    Data is sourced from the Scripps Institution of Oceanography (UCSD)
    Topex project.

    Modes:
      Regional (Default): Queries the CGI interface to generate an XYZ
        text file for the specific requested bounding box.

      Global (--global-grid): Downloads the full 'topo_27.1.img' binary
        grid file (~GBs).

    References:
      - https://topex.ucsd.edu/WWW_html/mar_grav.html
    """

    def __init__(self, mag: float = 1.0, global_grid: bool = False, **kwargs):
        super().__init__(name="margrav", **kwargs)
        # SIO 'mag' parameter controls sampling. 1.0 is full resolution.
        self.mag = float(mag)
        self.global_grid = global_grid

    def run(self):
        """Run the MarGrav fetching logic."""

        # Global Grid Download
        if self.global_grid:
            self.add_entry_to_results(
                url=MARGRAV_IMG_URL,
                dst_fn="topo_27.1.img",
                data_type="img",
                agency="SIO / UCSD",
                title="Global Predicted Topography (IMG)",
            )
            return self

        # Regional CGI Query
        if self.region is None:
            return []

        w, e, s, n = self.region

        data = {"north": n, "west": w, "south": s, "east": e, "mag": self.mag}

        full_url = f"{MARGRAV_CGI_URL}?{urlencode(data)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        out_fn = f"margrav_{r_str}.xyz"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="xyz",
            agency="SIO / UCSD",
            title="Marine Gravity Model (Regional)",
        )

        return self
