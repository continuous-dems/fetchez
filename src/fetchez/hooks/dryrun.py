#!/usr/bin/env python

"""
fetchez.hooks.dryrun
~~~~~~~~~~~~~

Empty the download queue before downloads begin.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class DryRun(FetchHook):
    name = "dryrun"
    meta_desc = "Clear the download queue (simulate only)."
    meta_stage = "manifest"  # pre
    meta_category = "pipeline"

    def run(self, entries):
        return []
