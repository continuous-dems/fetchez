"""
fetchez.modules.dtu
~~~~~~~~~~~~~~~~~~~
Fetch global gravity and altimetry grids from DTU Space.
"""

import os
import logging
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

DTU_BASE_URL = "ftp://ftp.space.dtu.dk/pub"


@cli.cli_opts(
    help_text="DTU Global Gravity/Altimetry Models",
    version='Model version (e.g., "10", "13", "15", "18", "21"). Default: 10',
    product='Product type: "mss", "lat", "mdt", "tide", "gravity". Default: "mss"',
    format='File format preference: "nc" (NetCDF) or "ascii". Default: "nc"',
)
class DTU(core.FetchModule):
    """Fetch global grids from the Technical University of Denmark (DTU).

    * This module is in development and may contain bugs *

    Examples:
        fetchez dtu --version 13 --product mss
        fetchez dtu --version 10 --product tide --format ascii
    """

    def __init__(self, version="10", product="mss", format="nc", **kwargs):
        super().__init__(name="dtu", **kwargs)
        self.version = str(version)
        self.product = product.lower()
        self.format_pref = format.lower()

    def run(self):
        ver_str = f"DTU{self.version}"
        prod_map = {
            "mss": "MSS",
            "lat": "LAT",
            "mdt": "MDT",
            "grav": "GRAVITY",
            "err": "err",
            "bat": "bat",
            "gra": "gra",
        }

        if self.product not in prod_map and self.product != "tide":
            logger.error(f"Unknown product: {self.product}")
            return self

        # if self.product == "tide":
        #     base_dir = f"{ver_str}_TIDEMODEL"
        # else:
        #     base_dir = f"{ver_str}{prod_map[self.product]}"

        # res_map = []

        prod = prod_map[self.product]
        url = f"{DTU_BASE_URL}/{ver_str}/1_MIN/{ver_str}{prod.upper()}_1min.{prod.lower()}.gz"
        self.add_entry_to_results(
            url=url,
            dst_fn=os.path.basename(url),
            data_type="grid",
            agency="DTU Space",
            title=f"DTU {self.version} {self.product.upper()}",
        )

        return self
