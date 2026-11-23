#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.cli
~~~~~~~~~~~~~~~~

Deprecated CLI utilities; use fetchez.cli.utils.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

from fetchez.cli.utils import (
    FetchezMainGroup,
    FetchezMainCommand,
    truncate_string,
)

__all__ = [
    "FetchezMainGroup",
    "FetchezMainCommand",
    "truncate_string",
]
