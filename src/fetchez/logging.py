#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.logging
~~~~~~~~~~~~~~~~

Compatibility exports for Fetchez logging.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

from .utils.logging import (
    configure_logging,
    TqdmLoggingHandler,
)

__all__ = [
    "configure_logging",
    "TqdmLoggingHandler",
]
