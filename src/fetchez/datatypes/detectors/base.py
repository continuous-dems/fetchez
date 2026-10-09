#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.datatypes.detectors.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2025 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Detection:
    data_type: str
    confidence: float
    detector: str
    reason: str = ""
    format: Optional[str] = None


class BaseDetector:
    """Base class for generic data-type detectors."""

    name = "base-detector"

    meta_desc = ""
    meta_category = "detection"
    meta_priority = 100

    def detect(self, entry):
        """Return a Detection result, or None."""
        raise NotImplementedError
