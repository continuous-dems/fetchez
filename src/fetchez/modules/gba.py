#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.gba
~~~~~~~~~~~~~~~~~~~

Fetch Global Building Atlas (GBA) data via WFS.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

GBA_WFS_URL = "https://tubvsig-so2sat-vm1.srv.mwn.de/geoserver/ows"


# =============================================================================
# GBA Module
# =============================================================================
@cli.cli_opts(
    help_text="Global Building Atlas (GBA)",
    layer="WFS Layer Name (default: 'lod1_global')",
    fmt="Output format: 'json' (GeoJSON) or 'shape-zip' (Shapefile)",
)
class GBA(core.FetchModule):
    """Fetch building footprints from the Global Building Atlas.

    The GBA provides Level of Detail 1 (LOD1) 3D building models (footprint + height)
    derived from satellite imagery. Data is fetched via a Web Feature Service (WFS).

    Common Layers:
      - lod1_global (Default)
      - lod1_europe

    References:
      - https://www.wk.bgu.tum.de/en/global-building-atlas/
    """

    def __init__(self, layer: str = "lod1_global", fmt: str = "json", **kwargs):
        super().__init__(name="gba", **kwargs)
        self.layer = layer
        self.fmt = fmt

    def run(self):
        """Run the GBA fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        format_map = {
            "json": "application/json",
            "geojson": "application/json",
            "shape-zip": "SHAPE-ZIP",
            "shp": "SHAPE-ZIP",
            "gml": "gml3",
        }
        out_fmt = format_map.get(self.fmt.lower(), "application/json")
        ext = "zip" if "zip" in out_fmt.lower() else "geojson"

        bbox_urn = f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326"

        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": self.layer,
            "bbox": bbox_urn,
            "outputFormat": out_fmt,
            "srsName": "EPSG:4326",
        }

        full_url = f"{GBA_WFS_URL}?{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        safe_layer = self.layer.replace(":", "_")
        out_fn = f"gba_{safe_layer}_{r_str}.{ext}"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="vector",
            agency="TUM / DLR",
            title=f"GBA {self.layer}",
        )

        return self
