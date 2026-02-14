#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.proj
~~~~~~~~~~~~~~~~~~~~

Fetch transformation grids via the PROJ Content Delivery Network (CDN).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging
from typing import Optional
from fetchez import core
from fetchez import cli
from fetchez import spatial

try:
    from shapely.geometry import shape

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)

PROJ_CDN_INDEX_URL = "https://cdn.proj.org/files.geojson"


@cli.cli_opts(
    help_text="PROJ CDN Transformation Grids",
    query='Search term (e.g., "geoid18", "vertcon", "nadcon").',
    epsg="Filter by source or target EPSG code.",
)
class PROJ(core.FetchModule):
    """Fetch vertical and horizontal transformation grids from PROJ.org.

    This module is the 'fast path' for standard grids like:
      - Geoids (GEOID18, EGM2008)
      - Shift Grids (VERTCON, NADCON)

    For NOAA Tidal Grids (MLLW, MHHW), use the 'vdatum' module.
    """

    def __init__(
        self, query: Optional[str] = None, epsg: Optional[str] = None, **kwargs
    ):
        super().__init__(name="proj", **kwargs)
        self.query = query.lower() if query else None
        self.epsg = str(epsg) if epsg else None
        self.headers = {"User-Agent": "Fetchez/1.0 (PROJ-Compatible)"}

    def _intersects(self, grid_geom, grid_bbox=None):
        """Check intersection using Shapely (precise) or BBox (fast fallback)."""

        if not self.region:
            return True

        # Geometry Check (if Shapely is available)
        if HAS_SHAPELY and grid_geom:
            try:
                user_poly = spatial.region_to_shapely(self.region)
                grid_poly = shape(grid_geom)

                return user_poly.intersects(grid_poly)
            except Exception as e:
                logger.debug(f"Shapely intersection failed: {e}, falling back to bbox.")

        # BBox Fallback (Fast but rough)
        if grid_bbox:
            gw, gs, ge, gn = grid_bbox
            rw, re, rs, rn = self.region
            # Standard "Not Disjoint" check
            return not (rw > ge or re < gw or rs > gn or rn < gs)

        return True

    # def _intersects(self, grid_bbox):
    #     """Check intersection: [w, s, e, n] vs region [w, e, s, n]"""

    #     #logger.info(f'grid bbox: {grid_bbox}')
    #     #logger.info(f'self.region: {self.region}')
    #     if not grid_bbox or not self.region: return True
    #     gw, gs, ge, gn = grid_bbox
    #     rw, re, rs, rn = self.region
    #     return not (rw > ge or re < gw or rs > gn or rn < gs)

    def run(self):
        idx_file = os.path.join(self._outdir, "proj_files.geojson")

        if not os.path.exists(idx_file):
            logger.info("Fetching PROJ CDN Index...")
            if core.Fetch(PROJ_CDN_INDEX_URL).fetch_file(idx_file) != 0:
                logger.error("Failed to fetch PROJ index.")
                return self

        try:
            with open(idx_file, "r") as f:
                features = json.load(f).get("features", [])

            matches = 0
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry")
                bbox = feat.get("bbox")

                if geom is None:
                    continue
                if not self._intersects(geom, bbox):
                    continue

                if self.query:
                    text = f"{props.get('name')} {props.get('source_crs_name')} {props.get('target_crs_name')} {props.get('url')}".lower()
                    if self.query not in text:
                        continue

                if self.epsg:
                    s, t = (
                        str(props.get("source_crs_code")),
                        str(props.get("target_crs_code")),
                    )
                    if self.epsg not in s and self.epsg not in t:
                        continue

                self.add_entry_to_results(
                    url=props["url"],
                    dst_fn=os.path.basename(props["url"]),
                    data_type="grid",
                    agency="PROJ",
                    title=props.get("name"),
                    source_code=props.get("target_crs_code"),
                    target_code=props.get("target_crs_code"),
                )
                matches += 1

            if matches == 0:
                logger.warning("No grids found in PROJ CDN.")

        except Exception as e:
            logger.error(f"Error reading index: {e}")

        return self
