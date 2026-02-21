#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.flatten
~~~~~~~~~~~~~

Flatten the output directory structure.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Flatten(FetchHook):
    """Flattens output directory structure.

    Args:
        mode (str):
            'module' (default) -> outdir/module/file.ext (Flattens subdirs INSIDE module)
            'root'             -> outdir/file.ext (Removes module folder)
            'cwd'              -> ./file.ext (Ignores outdir completely)
    """

    name = "flatten"
    stage = "pre"
    category = "file-op"

    def __init__(self, mode="module", **kwargs):
        super().__init__(**kwargs)
        self.mode = mode.lower()

    def run(self, entries):
        for mod, entry in entries:
            current_path = entry.get("dst_fn")
            if not current_path:
                continue

            filename = os.path.basename(current_path)
            if self.mode == "cwd":
                new_dir = os.getcwd()

            elif self.mode == "root":
                new_dir = mod.outdir if mod.outdir else os.getcwd()

            elif self.mode == "module":
                new_dir = mod._outdir

            entry["dst_fn"] = os.path.join(new_dir, filename)

        return entries
