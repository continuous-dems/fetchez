#!/usr/bin/env python

"""
fetchez.modules.dnc
~~~~~~~~~~~~~~~~~~~

Fetch Digital Nautical Chart (DNC) Bathymetry data via NRL WFS.
"""

import logging
from urllib.parse import urlencode

from fetchez import cli
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

DNC_WFS_URL = "https://geoint.nrlssc.navy.mil/dnc/wfs/BathyServices"


@cli.cli_opts(
    help_text="NRL Digital Nautical Chart (DNC) Bathymetry WFS",
    layer="WFS Layer Name (e.g., 'BathyServices:soundings')",
    fmt="Output format: 'json' (GeoJSON) or 'shape-zip' (Shapefile) (default: 'json')",
)
class DNC(FetchModule):
    name = "dnc"
    meta_category = "Bathymetry"
    meta_desc = "Navy DNC WFS (Digital Nautical Chart Vector Data)"
    meta_agency = "NRL"
    meta_tags = ["dnc", "nautical", "chart", "navy", "wfs", "bathymetry", "vector"]
    meta_region = "Global"
    meta_resolution = "Vector"
    meta_license = "US Govt / Public Domain"
    meta_urls = {"home": "https://geoint.nrlssc.navy.mil/"}

    def __init__(self, layer: str = "ALL_SOUNDINGS", fmt: str = "json", **kwargs):
        super().__init__(name="dnc", **kwargs)
        self.layer = layer
        self.fmt = fmt

    def run(self):
        """Run the DNC WFS fetching logic."""

        if self.wgs_region is None:
            logger.error("A spatial region is required to fetch WFS data.")
            return self

        w, e, s, n = self.wgs_region
        format_map = {
            "json": "application/json",
            "geojson": "application/json",
            "shape-zip": "SHAPE-ZIP",
            "shp": "SHAPE-ZIP",
        }
        out_fmt = format_map.get(self.fmt.lower(), "application/json")
        ext = "zip" if "zip" in out_fmt.lower() else "geojson"

        bbox_str = f"{w},{s},{e},{n},EPSG:4326"
        params = {
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": self.layer,
            "BBOX": bbox_str,
            "OUTPUTFORMAT": out_fmt,
            "SRSNAME": "EPSG:4326",
        }

        full_url = f"{DNC_WFS_URL}?{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        safe_layer = self.layer.replace(":", "_")
        out_fn = f"dnc_{safe_layer}_{r_str}.{ext}"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="dnc_geojson" if ext == "geojson" else "dnc_vector",
            agency="NRL",
            title=f"DNC WFS {self.layer}",
        )

        return self
