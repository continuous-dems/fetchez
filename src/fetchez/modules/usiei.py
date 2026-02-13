#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usiei
~~~~~~~~~~~~~~~~~~~~~

Query the US Interagency Elevation Inventory (USIEI) via ArcGIS REST API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

USIEI_MAP_SERVER_URL = (
    "https://coast.noaa.gov/arcgis/rest/services/"
    "USInteragencyElevationInventory/USIEIv2/MapServer"
)


# =============================================================================
# USIEI Module
# =============================================================================
@cli.cli_opts(
    help_text="US Interagency Elevation Inventory (USIEI)",
    layer="Layer ID: 0=TopoBathy, 1=Bathy, 2=Topo, 3=IfSAR. Default: 0",
    where="SQL filter clause (default: '1=1')",
)
class USIEI(core.FetchModule):
    """Query the US Interagency Elevation Inventory (USIEI).

    The USIEI is a comprehensive inventory of known high-accuracy topographic
    and bathymetric data for the United States.

    This module downloads the **inventory metadata** (footprints, dates, quality)
    as a GeoJSON file for the requested region. It does not download the actual
    DEMs/Lidar (use 'dav' or 'tnm' for that).

    **Layers:**
      - 0: Lidar - Topobathy (Default)
      - 1: Lidar - Bathymetry
      - 2: Lidar - Topography
      - 3: IfSAR / InSAR
      - 4: Other Bathymetry

    References:
      - https://coast.noaa.gov/inventory/
    """

    def __init__(self, layer: str = "0", where: str = "1=1", **kwargs):
        super().__init__(name="usiei", **kwargs)
        self.layer = int(layer)
        self.where = where

    def run(self):
        """Run the USIEI fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

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

        query_url = f"{USIEI_MAP_SERVER_URL}/{self.layer}/query"
        full_url = f"{query_url}?{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")

        layer_names = {0: "topobathy", 1: "bathy", 2: "topo", 3: "ifsar", 4: "other"}
        l_name = layer_names.get(self.layer, f"layer{self.layer}")

        out_fn = f"usiei_{l_name}_{r_str}.geojson"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="vector",
            agency="NOAA / USGS",
            title=f"USIEI Inventory ({l_name})",
        )

        return self
