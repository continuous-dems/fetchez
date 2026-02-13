#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.fabdem
~~~~~~~~~~~~~~~~~~~~~~

Fetch FABDEM (Forest And Buildings removed Copernicus DEM) data.

:copyright: (c) 2022 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging
from fetchez import core
from fetchez import cli
from fetchez import utils

logger = logging.getLogger(__name__)

FABDEM_FOOTPRINTS_URL = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/FABDEM_v1-2_tiles.geojson"
FABDEM_DATA_URL = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn"
FABDEM_INFO_URL = "https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn"


# =============================================================================
# FABDEM Module
# =============================================================================
@cli.cli_opts(help_text="FABDEM (Forest And Buildings removed Copernicus DEM)")
class FABDEM(core.FetchModule):
    """Fetch FABDEM elevation data.

    FABDEM is a global elevation map that removes building and tree height
    biases from the Copernicus GLO 30 Digital Elevation Model (DEM).
    The data is available at 1 arc-second grid spacing (~30m).

    This module downloads the tile index (GeoJSON) and finds tiles
    intersecting the requested region.

    References:
      - https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn
    """

    def __init__(self, **kwargs):
        super().__init__(name="fabdem", **kwargs)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fetchez/0.2",
            "Referer": FABDEM_INFO_URL,
        }

    def _intersects(self, search_bbox, feature_geom):
        """
        Check if a GeoJSON Polygon geometry intersects the search bbox.
        Search BBox format: [xmin, xmax, ymin, ymax] (Fetchez standard region)
        """

        s_w, s_e, s_s, s_n = search_bbox

        try:
            coords = feature_geom.get("coordinates", [])[0]  # Outer ring
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]

            f_w, f_e, f_s, f_n = min(xs), max(xs), min(ys), max(ys)

            if (s_w > f_e) or (s_e < f_w) or (s_s > f_n) or (s_n < f_s):
                return False
            return True

        except (IndexError, TypeError):
            return False

    def run(self):
        """Run the FABDEM fetching logic."""

        if self.region is None:
            return []

        idx_filename = os.path.basename(FABDEM_FOOTPRINTS_URL)
        local_json = os.path.join(self._outdir, idx_filename)

        logger.info("Fetching FABDEM tile index...")
        if (
            core.Fetch(FABDEM_FOOTPRINTS_URL, headers=self.headers).fetch_file(
                local_json
            )
            != 0
        ):
            logger.error("Failed to download FABDEM footprints.")
            return self

        matches = 0
        try:
            with open(local_json, "r") as f:
                data = json.load(f)

            features = data.get("features", [])
            logger.info(f"Scanning {len(features)} tiles...")

            for feature in features:
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})

                if self._intersects(self.region, geom):
                    zip_name = props.get("zipfile_name")

                    if zip_name:
                        url = f"{FABDEM_DATA_URL}/{zip_name}"

                        self.add_entry_to_results(
                            url=url,
                            dst_fn=zip_name,
                            data_type="zip",
                            agency="University of Bristol",
                            title=f"FABDEM Tile {zip_name}",
                        )
                        matches += 1

            if matches == 0:
                logger.warning("No FABDEM tiles found for this region.")
            else:
                logger.info(f"Found {matches} FABDEM tiles.")

        except Exception as e:
            logger.error(f"Error processing FABDEM index: {e}")

        if os.path.exists(local_json):
            os.remove(local_json)

        return self
