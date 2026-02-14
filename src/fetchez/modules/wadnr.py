#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.wadnr
~~~~~~~~~~~~~~~~~~~~~

Fetch LiDAR data from the Washington State Department of Natural Resources (WA DNR).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import math
import logging
from typing import Optional
from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

WA_DNR_BASE = "https://lidarportal.dnr.wa.gov"
WA_DNR_DOWNLOAD_URL = f"{WA_DNR_BASE}/download"
WA_DNR_REST_URL = f"{WA_DNR_BASE}/arcgis/rest/services/lidar/wadnr_hillshade/MapServer"
WA_DNR_LAYERS_URL = f"{WA_DNR_REST_URL}/layers?f=pjson"


def mercator_to_latlon(x, y):
    """Convert Web Mercator (EPSG:3857) to WGS84 (EPSG:4326).
    Simple math implementation to avoid heavy dependencies like pyproj.
    """

    lon = (x / 20037508.34) * 180
    lat = (y / 20037508.34) * 180
    lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
    return (lon, lat)


# =============================================================================
# WADNR Module
# =============================================================================
@cli.cli_opts(
    help_text="Washington State DNR LiDAR",
    filter="Filter projects by name (case-insensitive substring).",
    project_id="Filter by specific Project ID (integer).",
)
class WADNR(core.FetchModule):
    """Fetch LiDAR data from the Washington State DNR Portal.

    This module queries the WA DNR ArcGIS MapServer to find projects
    intersecting the requested region. It then generates download requests
    for the associated LiDAR point clouds (or derived products).

    References:
      - https://lidarportal.dnr.wa.gov/
    """

    def __init__(self, filter: Optional[str] = None, project_id: Optional[str] = None, **kwargs):
        super().__init__(name="wadnr", **kwargs)
        self.name_filter = filter.lower() if filter else None
        self.project_id = int(project_id) if project_id else None

    def _intersects_mercator(self, extent_3857):
        """Check intersection after converting extent to WGS84."""

        if not extent_3857 or not self.region:
            return False

        try:
            w_geo, s_geo = mercator_to_latlon(extent_3857["xmin"], extent_3857["ymin"])
            e_geo, n_geo = mercator_to_latlon(extent_3857["xmax"], extent_3857["ymax"])

            r_w, r_e, r_s, r_n = self.region

            if (r_w > e_geo) or (r_e < w_geo) or (r_s > n_geo) or (r_n < s_geo):
                return False
            return True
        except Exception:
            return False

    def run(self):
        """Run the WA DNR fetching logic."""

        if self.region is None:
            return []

        logger.info("Querying WA DNR Layer Metadata...")
        req = core.Fetch(WA_DNR_LAYERS_URL).fetch_req()

        if not req or req.status_code != 200:
            logger.error("Failed to fetch WA DNR layers.")
            return self

        try:
            data = req.json()
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from WA DNR.")
            return self

        layers = data.get("layers", [])
        logger.info(f"Scanning {len(layers)} projects...")

        matches = 0
        for layer in layers:
            name = layer.get("name", "Unknown")

            if self.name_filter and self.name_filter not in name.lower():
                continue

            extent = layer.get("extent")
            if not self._intersects_extent(extent):
                continue

            valid_id = None

            if self.project_id:
                pass

            sub_layers = layer.get("subLayers", [])
            if sub_layers:
                for sub in sub_layers:
                    try:
                        # WA DNR naming convention: "Name X" -> ID is X-1 usually
                        # This is fragile but preserved from original logic
                        parsed = int(sub["name"][:-1]) - 1
                        valid_id = parsed
                        break
                    except (ValueError, TypeError, IndexError):
                        continue

            if valid_id is None:
                continue

            w, e, s, n = self.region
            geojson_poly = {
                "type": "Polygon",
                "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
            }

            params = {
                "ids": valid_id,  # Can be list, here we do one by one
                "format": "json",
                "geojson": json.dumps(geojson_poly),
            }

            dl_req_url = f"{WA_DNR_DOWNLOAD_URL}?{urlencode(params)}"

            try:
                r = core.Fetch(dl_req_url).fetch_req()
                if r and r.status_code == 200:
                    try:
                        resp_json = r.json()
                        final_url = resp_json.get("url")
                    except:
                        final_url = r.url  # If it was a redirect

                    if final_url:
                        self.add_entry_to_results(
                            url=final_url,
                            dst_fn=f"wa_dnr_{valid_id}_{name.replace(' ', '_')}.zip",
                            data_type="lidar",
                            agency="WA DNR",
                            title=name,
                        )
                        matches += 1
            except Exception as e:
                logger.warning(f"Failed to resolve download for {name}: {e}")

        logger.info(f"Found {matches} WA DNR projects.")
        return self

    def _intersects_extent(self, extent_3857):
        """Wrapper for readability."""

        return self._intersects_mercator(extent_3857)
