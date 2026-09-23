#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Resolve prioritized authoritative footprints into accepted spatial claims.

This hook is intentionally dataset-agnostic. Entries opt in by carrying a
priority value and an authoritative geometry. Entries at the same priority are
processed as a group: they may overlap each other, while all lower-priority
entries are clipped by the union of higher-priority authoritative footprints.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import logging
from typing import Any

import shapely
import shapely.wkb
import shapely.wkt
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from fetchez import spatial
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class SpatialClaimHook(FetchHook):
    """Resolve partial spatial claims without imposing dataset-specific policy."""

    name = "spatial-claim"
    meta_aliases = ["spatial_claim"]
    meta_stage = "manifest"
    meta_category = "manifest-filter"
    meta_desc = (
        "Resolve authoritative source footprints by priority while preserving "
        "partial lower-priority coverage."
    )

    def __init__(
        self,
        priority_key: str = "claim_priority",
        geometry_key: str = "claim_geometry",
        accepted_key: str = "accepted_geometry",
        excluded_key: str = "excluded_geometry",
        required_key: str = "claim_required",
        reverse: bool = True,
        drop_empty: bool = True,
        fallback_bbox: bool = False,
        audit_output: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.priority_key = priority_key
        self.geometry_key = geometry_key
        self.accepted_key = accepted_key
        self.excluded_key = excluded_key
        self.required_key = required_key
        self.reverse = str(reverse).lower() in {"true", "1", "yes", "y"}
        self.drop_empty = str(drop_empty).lower() in {"true", "1", "yes", "y"}
        self.fallback_bbox = str(fallback_bbox).lower() in {
            "true",
            "1",
            "yes",
            "y",
        }
        self.audit_output = audit_output

    @staticmethod
    def _value(entry: dict[str, Any], key: str):
        value = entry.get(key)
        if value is None and isinstance(entry.get("metadata"), dict):
            value = entry["metadata"].get(key)
        return value

    @staticmethod
    def _coerce_geometry(value: Any) -> BaseGeometry | None:
        if value is None:
            return None
        if isinstance(value, BaseGeometry):
            return value
        if isinstance(value, (bytes, bytearray)):
            return shapely.wkb.loads(value)
        if isinstance(value, str):
            return shapely.wkt.loads(value)
        if isinstance(value, dict):
            return shape(value)
        raise TypeError(f"Unsupported claim geometry type: {type(value).__name__}")

    def _entry_geometry(self, entry: dict[str, Any]) -> BaseGeometry:
        value = self._value(entry, self.geometry_key)
        geometry = self._coerce_geometry(value)
        if geometry is None and self.fallback_bbox:
            bbox = entry.get("bbox") or entry.get("bounds")
            if bbox and len(bbox) == 4 and all(v is not None for v in bbox):
                geometry = spatial.region_to_shapely(bbox)

        if geometry is None:
            metadata = entry.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            identity = (
                entry.get("title")
                or metadata.get("dataset")
                or entry.get("url")
                or "unknown entry"
            )
            raise RuntimeError(
                f"spatial-claim requires authoritative geometry in '{self.geometry_key}' "
                f"for {identity!r}"
            )
        if geometry.is_empty or not geometry.is_valid:
            raise RuntimeError("spatial-claim received empty or invalid geometry")
        return geometry

    @staticmethod
    def _priority_sort_value(value: Any):
        # Prefer true numeric ordering when possible. Otherwise use a string.
        try:
            number = float(value)
        except (TypeError, ValueError):
            return (0, str(value))
        if not math.isfinite(number):
            raise RuntimeError("spatial-claim requires a finite priority")
        return (1, number)

    @staticmethod
    def _to_wkt(geometry: BaseGeometry) -> str:
        return shapely.to_wkt(geometry, rounding_precision=-1)

    def _write_audit(self, targeted):
        """Persist a generic diagnostic record of spatial claims.

        The feature geometry is the authoritative input claim. Accepted and
        excluded geometries are stored as WKT properties so validation can
        prove hierarchy behavior without coupling this hook to any dataset.
        """
        if not self.audit_output:
            return

        features = []
        for order, mod, entry, priority, geometry in targeted:
            metadata = (
                entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            )
            properties = {
                "order": order,
                "module": getattr(mod, "name", entry.get("module", "")),
                "priority": priority,
                "dataset": metadata.get("dataset", ""),
                "product": entry.get("claim_product", ""),
                "url": entry.get("url", ""),
                "accepted_wkt": entry.get(self.accepted_key, ""),
                "excluded_wkt": entry.get(self.excluded_key, ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geometry),
                    "properties": properties,
                }
            )

        out = Path(self.audit_output)
        if out.parent != Path("."):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, indent=2)
            + "\n"
        )

    def run(self, entries):
        if not entries:
            return entries

        targeted = []
        passthrough = []
        for order, (mod, entry) in enumerate(entries):
            priority = self._value(entry, self.priority_key)
            required = bool(self._value(entry, self.required_key))
            if priority is None:
                if required:
                    raise RuntimeError(
                        f"spatial-claim requires '{self.priority_key}' for a marked entry"
                    )
                passthrough.append((order, mod, entry))
                continue
            geometry = self._entry_geometry(entry)
            targeted.append((order, mod, entry, priority, geometry))

        if not targeted:
            return entries

        groups: dict[tuple[int, Any], list] = {}
        for item in targeted:
            # Equivalent numeric representations must share one priority group.
            key = self._priority_sort_value(item[3])
            groups.setdefault(key, []).append(item)

        ordered_priorities = sorted(groups, reverse=self.reverse)

        cumulative: BaseGeometry | None = None
        selected = list(passthrough)
        dropped = 0

        for priority in ordered_priorities:
            group = groups[priority]
            original_geometries = [item[4] for item in group]

            # Every entry in one priority group sees only claims from STRICTLY
            # higher groups. Equal-priority sources therefore never supersede
            # one another.
            for order, mod, entry, _, geometry in group:
                if cumulative is None or cumulative.is_empty:
                    accepted = geometry
                    excluded = None
                else:
                    accepted = geometry.difference(cumulative)
                    excluded = geometry.intersection(cumulative)

                existing_excluded = self._coerce_geometry(entry.get(self.excluded_key))
                if existing_excluded is not None and not existing_excluded.is_empty:
                    # Manifest policy may have already excluded part of this
                    # source (for example an older edition of the same tile).
                    # Keep the original authoritative claim for lower tiers,
                    # but never admit those pre-excluded cells at this tier.
                    accepted = accepted.difference(existing_excluded)
                    excluded = (
                        existing_excluded
                        if excluded is None or excluded.is_empty
                        else shapely.union_all([existing_excluded, excluded])
                    )

                if excluded is None or excluded.is_empty:
                    entry.pop(self.excluded_key, None)
                else:
                    entry[self.excluded_key] = self._to_wkt(excluded)

                if accepted.is_empty:
                    entry.pop(self.accepted_key, None)
                    if self.drop_empty:
                        dropped += 1
                        continue
                else:
                    entry[self.accepted_key] = self._to_wkt(accepted)

                selected.append((order, mod, entry))

            group_claim = shapely.union_all(original_geometries)
            cumulative = (
                group_claim
                if cumulative is None
                else shapely.union_all([cumulative, group_claim])
            )

        if dropped:
            logger.info("[spatial-claim] Dropped %d fully superseded entries.", dropped)

        self._write_audit(targeted)

        # Preserve original entry ordering. Priority determines geometry claims,
        # not downstream stream/module order.
        selected.sort(key=lambda item: item[0])
        return [(mod, entry) for _, mod, entry in selected]
