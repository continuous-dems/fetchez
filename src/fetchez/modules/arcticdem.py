#!/usr/bin/env python

"""
fetchez.modules.arcticdem
~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch ArcticDEM high-resolution digital surface models.
(Lightweight version: Uses pyproj + pyshp instead of GDAL)

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path

from pyogrio.raw import read
from pyproj import Transformer

from fetchez import cli, core, utils
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

ARCTIC_DEM_INDEX_URL = "https://data.pgc.umn.edu/elev/dem/setsm/ArcticDEM/indexes/ArcticDEM_Tile_Index_Rel7.zip"


# =============================================================================
# ArcticDEM Module
# =============================================================================
@cli.cli_opts(
    help_text="ArcticDEM (PGC/NGA/NSF)",
    where="Filter by attribute (Not fully supported in light mode, uses manual check)",
)
class ArcticDEM(FetchModule):
    name = "arcticdem"
    meta_category = "Topography"
    meta_desc = "ArcticDEM (Polar Geospatial Center)"
    meta_agency = "PGC / NGA"
    meta_tags = ["arctic", "dem", "topography", "elevation", "polar"]
    meta_region = "Arctic"
    meta_resolution = "2m, 10m, 32m"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://www.pgc.umn.edu/data/arcticdem/"}

    """Fetch ArcticDEM data (Digital Surface Models).

    ArcticDEM is an NGA-NSF public-private initiative to automatically
    produce a high-resolution, high quality, digital surface model (DSM)
    of the Arctic.

    This module uses 'pyproj' and 'pyogrio'.
    """

    def __init__(self, where: str | None = None, **kwargs):
        super().__init__(name="arcticdem", **kwargs)
        self.where = where

    def _get_projected_bbox(self):
        """Transform the WGS84 region [w, e, s, n] to EPSG:3413 (Polar Stereo)
        and return the min/max bounds [xmin, ymin, xmax, ymax].
        """

        w, e, s, n = self.wgs_region

        # Initialize Transformer: WGS84 (4326) -> Arctic Polar Stereo (3413)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3413", always_xy=True)

        # Transform all 4 corners to account for rotation/skew in projection
        corners = [
            transformer.transform(w, s),
            transformer.transform(w, n),
            transformer.transform(e, n),
            transformer.transform(e, s),
        ]

        # Calculate bounding box of the transformed corners
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]

        return [min(xs), min(ys), max(xs), max(ys)]

    def _intersects(self, box_a, box_b):
        """Simple AABB (Axis-Aligned Bounding Box) intersection check."""

        # Box: [xmin, ymin, xmax, ymax]
        return not (
            box_b[0] > box_a[2]
            or box_b[2] < box_a[0]
            or box_b[1] > box_a[3]
            or box_b[3] < box_a[1]
        )

    def run(self):
        """Run the ArcticDEM fetches module."""

        if self.wgs_region is None:
            return self

        idx_zip_name = Path(ARCTIC_DEM_INDEX_URL).name
        local_zip = Path(self._outdir) / idx_zip_name

        if core.Fetch(ARCTIC_DEM_INDEX_URL).fetch_file(local_zip, verbose=True) != 0:
            logger.error("Failed to download ArcticDEM Index.")
            return self

        unzipped = utils.p_unzip(
            local_zip, ["shp", "shx", "dbf", "prj"], outdir=self._outdir
        )
        v_shp = next((f for f in unzipped if f.endswith(".shp")), None)

        if not v_shp:
            logger.error("No .shp found in index.")
            return self

        try:
            search_bbox = self._get_projected_bbox()
            logger.info(f"Search Bounds (EPSG:3413): {search_bbox}")

            bbox = (search_bbox[0], search_bbox[1], search_bbox[2], search_bbox[3])

            meta, fids, geometry_wkb, fields = read(v_shp, bbox=bbox)
            matches = 0

            if len(geometry_wkb) > 0:
                col_names = [str(col).lower() for col in meta.get("fields", [])]

                for i in range(len(geometry_wkb)):
                    props_lower = {
                        col.lower(): fields[n][i] for n, col in enumerate(col_names)
                    }
                    tile_url = props_lower.get("url") or props_lower.get("fileurl")

                    if not tile_url:
                        continue

                    _dst_fn = Path(str(tile_url)).name
                    self.add_entry_to_results(
                        url=str(tile_url),
                        dst_fn=_dst_fn,
                        data_type="arcticdem",
                        agency="PGC",
                        title="ArcticDEM Tile",
                    )
                    matches += 1

            logger.info(f"Found {matches} ArcticDEM tiles.")

        except Exception as e:
            logger.error(f"Error processing index: {e}")

        for f in unzipped:
            Path(f).unlink(missing_ok=True)

        return self
