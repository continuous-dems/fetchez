#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.rename
~~~~~~~~~~~~~

Rename an entry fn.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import re
import logging

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Rename(FetchHook):
    """Rename files using Regex substitution before download.

    Args:
        match (str): Regex pattern to match (e.g. 'export_(\\d+)')
        replace (str): Replacement string (e.g. 'site_\\1')
    """

    name = "rename"
    stage = "pre"
    category = "file-op"

    def __init__(self, match=None, replace="", **kwargs):
        super().__init__(**kwargs)
        self.match = match
        self.replace = replace

    def run(self, entries):
        if not self.match:
            return entries

        for mod, entry in entries:
            dst = entry.get("dst_fn")
            if not dst:
                continue

            dirname, basename = os.path.split(dst)

            try:
                new_basename = re.sub(self.match, self.replace, basename)
                if new_basename != basename:
                    entry["dst_fn"] = os.path.join(dirname, new_basename)
            except Exception as e:
                logger.error(f"Rename pattern failed for {basename}: {e}")

        return entries
