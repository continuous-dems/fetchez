#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tiger
~~~~~~~~~~~~~~~~~~~~~

Fetch US Census Bureau TIGER data (Boundaries) via the TIGERweb REST API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from urllib.parse import urlencode

from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

# The "Current" service contains the latest boundaries.
# We can also support "PhysicalFeatures" or "Transportation" if needed,
# but "tigerWMS_Current" is the main boundary service.
TIGER_BASE_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer"


# =============================================================================
# TIGER Module
# =============================================================================
@cli.cli_opts(
    help_text="US Census Bureau TIGERweb (Boundaries)",
    layer="Target Layer Name (e.g., 'States', 'Counties', 'Census Tracts', 'Blocks')",
    where="SQL-like filter clause (default: '1=1')",
    check_meta="Force a refresh of the layer ID metadata lookup",
)
class Tiger(core.FetchModule):
    """Fetch US Census Bureau boundary data (TIGER).

    Uses the TIGERweb GeoServices REST API to download vector features
    (GeoJSON) for the specified region.

    Common Layers:
      - States
      - Counties
      - Census Tracts
      - Census Block Groups
      - Census Blocks
      - Unified School Districts
      - American Indian Tribal Subdivisions
    """

    def __init__(
        self,
        layer: str = "Counties",
        where: str = "1=1",
        check_meta: bool = False,
        **kwargs,
    ):
        super().__init__(name="tiger", **kwargs)
        self.layer_name = layer
        self.where = where
        self.check_meta = check_meta
        self._layer_id = None

    def _get_layer_id(self, layer_name):
        """Find the Layer ID by name from the service metadata.
        TIGERweb layer IDs can change, so we lookup by name.
        """

        meta_url = f"{TIGER_BASE_URL}?f=json"

        try:
            req = core.Fetch(meta_url).fetch_req()
            if not req or req.status_code != 200:
                logger.error("Failed to fetch TIGERweb metadata.")
                return None

            data = req.json()
            layers = data.get("layers", [])

            clean_name = layer_name.lower().strip()

            for l in layers:
                if l["name"].lower().strip() == clean_name:
                    return l["id"]

            for layer in layers:
                if clean_name in layer["name"].lower():
                    logger.info(
                        f"Matched layer '{layer_name}' to '{layer['name']}' (ID: {layer['id']})"
                    )
                    return layer["id"]

            avail = [layer["name"] for layer in layers[:10]]  # Show first 10
            logger.error(
                f"Layer '{layer_name}' not found. Available examples: {avail}..."
            )
            return None

        except Exception as e:
            logger.error(f"Error looking up layer ID: {e}")
            return None

    def run(self):
        """Run the TIGER fetching logic."""

        if self.region is None:
            return []

        logger.info(f"Resolving Layer ID for '{self.layer_name}'...")
        self._layer_id = self._get_layer_id(self.layer_name)

        if self._layer_id is None:
            return self

        query_url = f"{TIGER_BASE_URL}/{self._layer_id}/query"

        w, e, s, n = self.region

        params = {
            "f": "geojson",
            "where": self.where,
            "outFields": "*",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",  # Input Region is WGS84
            "outSR": "4326",  # Output GeoJSON should be WGS84
        }

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        safe_layer = self.layer_name.replace(" ", "_").lower()
        out_fn = f"tiger_{safe_layer}_{r_str}.geojson"

        full_url = f"{query_url}?{urlencode(params, safe=',:')}"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="geojson",
            agency="US Census Bureau",
            title=f"TIGER {self.layer_name}",
        )

        return self
