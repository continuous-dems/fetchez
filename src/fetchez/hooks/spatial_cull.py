#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.entries.spatial_cull
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Spatially culls overlapping entries based on a prioritization attribute
(like year or resolution) to prevent redundant data downloads.
Supports generic sub-grouping to prevent distinct datasets from culling each other.
"""

import logging
from collections import defaultdict
from shapely.geometry import Polygon, box
import shapely.wkb
import shapely.wkt

from fetchez.hooks import FetchHook
from fetchez.utils import parse_arg_to_list

logger = logging.getLogger(__name__)


class SpatialCullHook(FetchHook):
    """Evaluates entry geometries against a growing coverage mask.
    Drops entries that are completely covered by higher-priority data.
    """

    name = "spatial_cull"
    meta_stage = "manifest"
    meta_desc = "Cull spatially overlapping records based on priority attributes."

    def __init__(
        self,
        sort_by="year",
        group_by=None,
        reverse=True,
        min_coverage=0.99,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sort_by = sort_by
        self.group_by = parse_arg_to_list(group_by, str) if group_by else []
        self.reverse = str(reverse).lower() in ["true", "1", "yes"]
        self.min_coverage = float(min_coverage)

    def _get_entry_val(self, entry, key_name):
        """Helper to extract top-level or nested metadata values."""
        val = entry.get(key_name)
        if val is None and "metadata" in entry:
            val = entry["metadata"].get(key_name)
        return val

    def _cull_group(self, group_items):
        """Runs the spatial intersection cascade on a single isolated group."""

        def get_sort_val(item):
            _, entry = item
            val = self._get_entry_val(entry, self.sort_by)
            if val is None:
                return ""
            try:
                return float(val)
            except (ValueError, TypeError):
                return str(val)

        sorted_items = sorted(group_items, key=get_sort_val, reverse=self.reverse)

        cumulative_mask = Polygon()
        culled_entries = []
        dropped_count = 0

        for mod, entry in sorted_items:
            geom = entry.get("geometry")

            if not geom:
                bbox = entry.get("bbox")
                if bbox and len(bbox) == 4:
                    geom = box(*bbox)

            if not geom:
                culled_entries.append((mod, entry))
                continue

            if isinstance(geom, (bytes, bytearray)):
                geom = shapely.wkb.loads(geom)
            elif isinstance(geom, str):
                geom = shapely.wkt.loads(geom)

            if cumulative_mask.is_valid and geom.is_valid:
                intersection = cumulative_mask.intersection(geom)
                coverage = intersection.area / geom.area if geom.area > 0 else 0

                if coverage >= self.min_coverage:
                    dropped_count += 1
                    title = (
                        self._get_entry_val(entry, "title")
                        or entry.get("dst_fn")
                        or "item"
                    )
                    logger.debug(
                        f"[spatial_cull] Dropping '{title}' ({coverage:.1%} covered)"
                    )
                    continue

                cumulative_mask = cumulative_mask.union(geom)

            culled_entries.append((mod, entry))

        return culled_entries, dropped_count

    def run(self, entries):
        if not entries:
            return entries

        # Group entries by the requested metadata keys
        grouped_buckets = defaultdict(list)

        for mod, entry in entries:
            if self.group_by:
                group_key = tuple(
                    str(self._get_entry_val(entry, k)) for k in self.group_by
                )
            else:
                group_key = ("default",)

            grouped_buckets[group_key].append((mod, entry))

        final_entries = []
        total_dropped = 0

        for group_key, group_items in grouped_buckets.items():
            if self.group_by:
                logger.debug(
                    f"[spatial_cull] Culling subgroup: {self.group_by} = {group_key}"
                )

            retained, dropped = self._cull_group(group_items)
            final_entries.extend(retained)
            total_dropped += dropped

        if total_dropped > 0:
            logger.info(
                f"[spatial_cull] Culled {total_dropped} redundant entries based on '{self.sort_by}'."
            )

        return final_entries
