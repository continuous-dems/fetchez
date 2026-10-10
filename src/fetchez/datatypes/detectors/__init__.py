#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.datatypes.detectors
~~~~~~~~~~~~~~~~~~~~~~

 Detectors init

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from .base import BaseDetector, Detection


def detect_entry(
    entry,
    *,
    overwrite=False,
    replace_unknown=True,
):
    """Enrich an entry with a detected generic data type.

    Registered data types and legacy profile identifiers are preserved
    unless overwrite is explicitly requested.

    Unknown data types may be replaced when detection succeeds.
    """

    from fetchez.registry import (
        DataTypeRegistry,
        DetectorRegistry,
        ProfileRegistry,
    )

    current = entry.get("data_type")

    if current and not overwrite:
        if DataTypeRegistry.exists(current):
            return entry

        # Legacy compatibility: data_type may contain a profile name.
        ProfileRegistry.load_all()
        if ProfileRegistry.get_yaml(current) is not None:
            return entry

        if not replace_unknown:
            return entry

    result = DetectorRegistry.detect(entry)

    if result is None:
        return entry

    if current and current != result.data_type:
        entry.setdefault("original_data_type", current)

    entry["data_type"] = result.data_type

    return entry


# def detect_entry(entry, *, overwrite=False):
#     """Populate an entry's data_type using registered detectors."""
#     if entry.get("data_type") and not overwrite:
#         return entry

#     from fetchez.registry import DetectorRegistry

#     result = DetectorRegistry.detect(entry)

#     if result is not None:
#         entry["data_type"] = result.data_type

#     return entry


__all__ = ["BaseDetector", "Detection", "detect_entry"]
