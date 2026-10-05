#!/usr/bin/env python

"""
fetchez.modules.nswtb
~~~~~~~~~~~~~~~~~~~~~

Fetch New South Wales (NSW) Topo-Bathy data via ArcGIS REST API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode

from fetchez import cli
from fetchez.modules import FetchModule

NSW_MAP_SERVER = (
    "https://mapprod2.environment.nsw.gov.au/arcgis/rest/services/"
    "Coastal_Marine/NSW_Marine_Lidar_Bathymetry_Data_2018/MapServer"
)


# =============================================================================
# NSW_TB Module
# =============================================================================
@cli.cli_opts(
    help_text="NSW Marine LiDAR Topo-Bathy 2018",
    layer="Layer ID: 0=Contours (5m), 1=Slope, 2=Bathymetry DEM. Default: 0",
    where="SQL filter clause (default: '1=1')",
)
class NSWTB(FetchModule):
    name = "nswtb"
    meta_category = "Bathymetry"
    meta_desc = "NSW Marine LiDAR Topo-Bathy (Contours/DEM)"
    meta_agency = "NSW Government"
    meta_tags = ["nsw", "australia", "bathymetry", "lidar", "contours", "topo-bathy"]
    meta_region = "Australia (NSW Coast)"
    meta_resolution = "5m Contours / 5m DEM"
    meta_license = "Creative Commons Attribution"
    meta_urls = {
        "home": "https://datasets.seed.nsw.gov.au/dataset/marine-lidar-topo-bathy-2018"
    }

    """Fetch New South Wales (NSW) Marine LiDAR Topo-Bathy data.

    This dataset covers the NSW coast using Airborne LiDAR Bathymetry (ALB)
    collected in 2018. It provides high-resolution nearshore data.

    **Layers:**
      - 0: Isobaths (Contours) at 5m depth intervals
      - 1: Slope (Degrees)
      - 2: Bathymetry DEM (Metrs)

    Data is fetched via the NSW Environment ArcGIS REST API.

    References:
      - https://datasets.seed.nsw.gov.au/dataset/marine-lidar-topo-bathy-2018
    """

    def __init__(self, layer: str = "0", where: str = "1=1", **kwargs):
        super().__init__(name="nswtb", **kwargs)
        self.layer = int(layer)
        self.where = where

    def run(self):
        """Run the NSW_TB fetching logic."""

        if self.wgs_region is None:
            return []

        w, e, s, n = self.wgs_region

        # For DEMs, we might need an 'export' operation.
        params = {
            "where": self.where,
            "outFields": "*",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "f": "geojson",
            "returnGeometry": "true",
        }

        base_query_url = f"{NSW_MAP_SERVER}/{self.layer}/query"
        full_url = f"{base_query_url}?{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        layer_name = {0: "contours", 1: "slope", 2: "dem"}.get(
            self.layer, f"layer{self.layer}"
        )

        out_fn = f"nswtb_{layer_name}_{r_str}.geojson"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="vector" if self.layer == 0 else "json",
            agency="NSW Govt",
            title=f"NSW Topo-Bathy {layer_name.title()}",
        )

        return self
