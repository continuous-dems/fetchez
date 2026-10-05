#!/usr/bin/env python

"""
fetchez.hooks.list_entries
~~~~~~~~~~~~~

List the urls gathered from the module.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import sys
import threading

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()


class ListEntries(FetchHook):
    name = "list"
    meta_desc = "Print discovered URLs or filepaths to stdout."
    meta_stage = "manifest"  # pre
    meta_category = "metadata"

    def run(self, entries):
        for _mod, entry in entries:
            with PRINT_LOCK:
                sys.stdout.write(entry.get("url", "") + "\n")
                sys.stdout.flush()
        return entries
