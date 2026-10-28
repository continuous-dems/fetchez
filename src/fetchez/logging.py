#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.logging
~~~~~~~~~~~~~~~~

Logging configuration for Fetchez.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import logging

from .utils import TqdmLoggingHandler


def configure_logging(
    name="fetchez",
    *,
    quiet=False,
    verbose=False,
    level=None,
    handler=None,
    propagate=True,
):
    if level is None:
        level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    for existing in logger.handlers[:]:
        if getattr(existing, "_fetchez_managed", False):
            logger.removeHandler(existing)
            existing.close()

    if handler is None:
        handler = TqdmLoggingHandler()

    handler.setFormatter(logging.Formatter("[ %(levelname)s ] %(name)s: %(message)s"))
    handler._fetchez_managed = True
    logger.addHandler(handler)

    return logger
