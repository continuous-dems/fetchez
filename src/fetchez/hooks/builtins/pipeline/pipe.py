#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.pipeline.pipe
~~~~~~~~~~~~~

Pipe the dst_fn to stdout.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import logging
import threading

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()


class PipeOutput(FetchHook):
    name = "pipe"
    desc = "Print absolute file paths to stdout for piping."
    stage = "post"
    category = "pipeline"

    def run(self, entries):
        """Input is: [url, path, type, status]"""

        for mod, entry in entries:
            if entry.get("status") == 0:
                with PRINT_LOCK:
                    print(
                        os.path.abspath(entry.get("dst_fn")),
                        file=sys.stdout,
                        flush=True,
                    )
        return entries
