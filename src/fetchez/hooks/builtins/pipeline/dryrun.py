#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.pipeline.dryrun
~~~~~~~~~~~~~

Empty the download queue in before downloads begin.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class DryRun(FetchHook):
    name = "dryrun"
    desc = "Clear the download queue (simulate only)."
    stage = "pre"
    category = "pipeline"

    def run(self, entries):
        # Return empty list to stop execution
        return []
