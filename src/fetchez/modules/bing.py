#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.bing
~~~~~~~~~~~~~~~~~~~~

Fetch Microsoft Global ML Building Footprints.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import csv
import logging
from fetchez import core
from fetchez import cli
from fetchez import utils

# Soft Dependency: mercantile (for QuadKey calculation)
try:
    import mercantile

    HAS_MERCANTILE = True
except ImportError:
    HAS_MERCANTILE = False

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================
BING_CSV_URL = (
    "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
)
BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fetchez/0.2",
    "Referer": "https://github.com/microsoft/GlobalMLBuildingFootprints",
}


# =============================================================================
# Bing Module
# =============================================================================
@cli.cli_opts(
    help_text="Microsoft Bing Building Footprints",
    zoom="Zoom level for QuadKey calculation (Default: 9)",
)
class Bing(core.FetchModule):
    """Fetch building footprints from Microsoft's Global ML Building Footprints.

    This dataset provides building footprints generated from Bing satellite imagery
    using Deep Learning. The data is distributed as GeoJSON files tiled by
    Bing Maps QuadKeys.

    **Dependencies:**
    - `mercantile`: Required to calculate QuadKeys (`pip install mercantile`)

    References:
      - https://github.com/microsoft/GlobalMLBuildingFootprints
    """

    def __init__(self, zoom: int = 9, **kwargs):
        super().__init__(name="bing", **kwargs)
        self.zoom = int(zoom)
        self.headers = BING_HEADERS

    def run(self):
        """Run the Bing BFP fetching logic."""

        if self.region is None:
            return []

        if not HAS_MERCANTILE:
            logger.error(
                'The "bing" module requires "mercantile". Install it via: pip install mercantile'
            )
            return self

        w, e, s, n = self.region
        quad_keys = set()

        tiles = list(mercantile.tiles(w, s, e, n, zooms=self.zoom))
        for tile in tiles:
            quad_keys.add(int(mercantile.quadkey(tile)))

        logger.info(f"Region covers {len(quad_keys)} QuadKeys (Zoom {self.zoom}).")

        csv_filename = os.path.basename(BING_CSV_URL)
        local_csv = os.path.join(self._outdir, csv_filename)

        if core.Fetch(BING_CSV_URL).fetch_file(local_csv, verbose=True) != 0:
            logger.error("Failed to download Bing dataset index.")
            return self

        matches = 0
        try:
            with open(local_csv, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header

                for row in reader:
                    if not row or len(row) < 3:
                        continue

                    try:
                        qk = int(row[1])

                        if qk in quad_keys:
                            location = row[0]  # e.g., 'UnitedStates'
                            url = row[2]

                            ext = "geojson.gz"
                            if url.endswith(".json.gz"):
                                ext = "json.gz"
                            elif url.endswith(".zip"):
                                ext = "zip"

                            dst_fn = f"bing_{location}_{qk}.{ext}"

                            self.add_entry_to_results(
                                url=url,
                                dst_fn=dst_fn,
                                data_type="geojson",
                                agency="Microsoft",
                                title=f"Bing Buildings {qk}",
                            )
                            matches += 1

                    except ValueError:
                        continue  # Skip malformed rows

        except Exception as e:
            logger.error(f"Error reading Bing index CSV: {e}")

        logger.info(f"Found {matches} matching dataset tiles.")
        return self
