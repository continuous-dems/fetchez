#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.entries.spatial_cull
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Spatially culls overlapping entries based on a prioritization attribute
(like year or resolution) to prevent redundant data downloads.
"""

import logging
from shapely.geometry import Polygon, box
import shapely.wkb
import shapely.wkt

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class SpatialCullHook(FetchHook):
    """Evaluates entry geometries against a growing coverage mask.
    Drops entries that are completely covered by higher-priority data.
    """

    name = "spatial_cull"
    meta_stage = "manifest"
    meta_desc = "Cull spatially overlapping records based on priority attributes."

    def __init__(self, sort_by="year", reverse=True, min_coverage=0.99, **kwargs):
        super().__init__(**kwargs)
        self.sort_by = sort_by
        self.reverse = str(reverse).lower() in ["true", "1", "yes"]
        self.min_coverage = float(min_coverage)

    def run(self, entries):
        if not entries:
            return entries

        # Sort entries to ensure highest priority items build the mask first
        def get_sort_val(item):
            _, entry = item
            val = entry.get(self.sort_by)
            return float(val) if val is not None else 0.0

        sorted_items = sorted(entries, key=get_sort_val, reverse=self.reverse)

        cumulative_mask = Polygon()
        culled_entries = []
        dropped_count = 0

        for mod, entry in sorted_items:
            geom = entry.get("geometry")

            # Fallback to bounding box if strict geometry is missing
            if not geom:
                bbox = entry.get("bbox")
                if bbox and len(bbox) == 4:
                    geom = box(*bbox)

            if not geom:
                culled_entries.append((mod, entry))
                continue

            # Coerce various geometry formats into Shapely objects
            if isinstance(geom, (bytes, bytearray)):
                geom = shapely.wkb.loads(geom)
            elif isinstance(geom, str):
                geom = shapely.wkt.loads(geom)

            if cumulative_mask.is_valid and geom.is_valid:
                intersection = cumulative_mask.intersection(geom)
                coverage = intersection.area / geom.area if geom.area > 0 else 0

                if coverage >= self.min_coverage:
                    dropped_count += 1
                    logger.debug(
                        f"[spatial_cull] Dropping '{entry.get('title')}' ({coverage:.1%} covered)"
                    )
                    continue

                cumulative_mask = cumulative_mask.union(geom)

            culled_entries.append((mod, entry))

        if dropped_count > 0:
            logger.info(
                f"[spatial_cull] Culled {dropped_count} redundant entries based on '{self.sort_by}'."
            )

        return culled_entries
