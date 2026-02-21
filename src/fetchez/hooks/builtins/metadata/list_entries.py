#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.metadata.list_entries
~~~~~~~~~~~~~

List the urls gathered from the module.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class ListEntries(FetchHook):
    name = "list"
    desc = "Print discovered URLs to stdout."
    stage = "pre"
    category = "metadata"

    def run(self, entries):
        for mod, entry in entries:
            print(entry.get("url", ""))
        return entries
