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


def detect_entry(entry, *, overwrite=False):
    """Populate an entry's data_type using registered detectors."""
    if entry.get("data_type") and not overwrite:
        return entry

    from fetchez.registry import DetectorRegistry

    result = DetectorRegistry.detect(entry)

    if result is not None:
        entry["data_type"] = result.data_type

    return entry


__all__ = ["BaseDetector", "Detection", "detect_entry"]
