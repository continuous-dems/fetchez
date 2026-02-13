#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.arcticdem
~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch ArcticDEM high-resolution digital surface models.
(Lightweight version: Uses pyproj + pyshp instead of GDAL)

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from fetchez import core
from fetchez import cli
from fetchez import utils

# Lightweight Dependencies
try:
    import shapefile  # pip install pyshp
    from pyproj import Transformer
    HAS_LIGHT_GEO = True
except ImportError:
    HAS_LIGHT_GEO = False

logger = logging.getLogger(__name__)

ARCTIC_DEM_INDEX_URL = 'https://data.pgc.umn.edu/elev/dem/setsm/ArcticDEM/indexes/ArcticDEM_Tile_Index_Rel7.zip'

# =============================================================================
# ArcticDEM Module
# =============================================================================
@cli.cli_opts(
    help_text="ArcticDEM (PGC/NGA/NSF)",
    where="Filter by attribute (Not fully supported in light mode, uses manual check)"
)
class ArcticDEM(core.FetchModule):
    """Fetch ArcticDEM data (Digital Surface Models).

    ArcticDEM is an NGA-NSF public-private initiative to automatically
    produce a high-resolution, high quality, digital surface model (DSM)
    of the Arctic.

    This module uses 'pyproj' and 'pyshp'.
    """

    def __init__(self, where: str = None, **kwargs):
        super().__init__(name='arcticdem', **kwargs)
        self.where = where

    def _get_projected_bbox(self):
        """Transform the WGS84 region [w, e, s, n] to EPSG:3413 (Polar Stereo)
        and return the min/max bounds [xmin, ymin, xmax, ymax].
        """

        w, e, s, n = self.region

        # Initialize Transformer: WGS84 (4326) -> Arctic Polar Stereo (3413)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3413", always_xy=True)

        # Transform all 4 corners to account for rotation/skew in projection
        corners = [
            transformer.transform(w, s),
            transformer.transform(w, n),
            transformer.transform(e, n),
            transformer.transform(e, s)
        ]

        # Calculate bounding box of the transformed corners
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]

        return [min(xs), min(ys), max(xs), max(ys)]


    def _intersects(self, box_a, box_b):
        """Simple AABB (Axis-Aligned Bounding Box) intersection check."""

        # Box: [xmin, ymin, xmax, ymax]
        return not (box_b[0] > box_a[2] or
                    box_b[2] < box_a[0] or
                    box_b[1] > box_a[3] or
                    box_b[3] < box_a[1])


    def run(self):
        """Run the ArcticDEM fetches module."""

        if self.region is None:
            return self

        if not HAS_LIGHT_GEO:
            logger.error("Missing libraries. Please run: pip install pyproj pyshp")
            return self

        idx_zip_name = os.path.basename(ARCTIC_DEM_INDEX_URL)
        local_zip = os.path.join(self._outdir, idx_zip_name)

        if core.Fetch(ARCTIC_DEM_INDEX_URL).fetch_file(local_zip, verbose=True) != 0:
            logger.error("Failed to download ArcticDEM Index.")
            return self

        unzipped = utils.p_unzip(local_zip, ['shp', 'shx', 'dbf', 'prj'], outdir=self._outdir)
        v_shp = next((f for f in unzipped if f.endswith('.shp')), None)

        if not v_shp:
            logger.error("No .shp found in index.")
            return self

        try:
            search_bbox = self._get_projected_bbox()
            logger.info(f"Search Bounds (EPSG:3413): {search_bbox}")

            sf = shapefile.Reader(v_shp)

            fields = [x[0] for x in sf.fields][1:] # Skip deletion flag
            try:
                url_idx = fields.index('fileurl')
            except ValueError:
                url_idx = next((i for i, f in enumerate(fields) if 'url' in f.lower()), -1)

            matches = 0

            for shapeRec in sf.iterShapeRecords():
                if self._intersects(search_bbox, shapeRec.shape.bbox):

                    data_link = shapeRec.record[url_idx]

                    if data_link:
                        self.add_entry_to_results(
                            url=data_link,
                            dst_fn=os.path.basename(data_link),
                            data_type='arcticdem',
                            agency='PGC',
                            title='ArcticDEM Tile'
                        )
                        matches += 1

            logger.info(f"Found {matches} ArcticDEM tiles.")

        except Exception as e:
            logger.error(f"Error processing index: {e}")

        for f in unzipped:
            if os.path.exists(f): os.remove(f)

        return self
