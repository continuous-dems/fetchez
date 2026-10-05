#!/usr/bin/env python

"""
fetchez.hooks.pipe
~~~~~~~~~~~~~

Pipe the dst_fn to stdout.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import sys
import threading
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()


class PipeOutput(FetchHook):
    name = "pipe"
    meta_desc = "Print absolute file paths to stdout for piping."
    meta_stage = "collection"  # post
    meta_category = "pipeline"

    def run(self, entries):
        """Input is: [url, path, type, status]"""

        for _mod, entry in entries:
            if entry.get("status") == 0:
                dst_fn = entry.get("dst_fn")
                if dst_fn:
                    with PRINT_LOCK:
                        sys.stdout.write(str(Path(dst_fn).resolve()) + "\n")
                        sys.stdout.flush()
        return entries
