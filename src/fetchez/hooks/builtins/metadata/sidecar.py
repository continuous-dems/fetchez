#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.metadata.sidecar
~~~~~~~~~~~~~

Generates a 'sidecar' metadata file for each entry

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging
from datetime import datetime

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Sidecar(FetchHook):
    """Write a metadata sidecar file (.meta.json) for every download.
    Useful for data provenance (tracking source URLs and dates).
    """

    name = "sidecar"
    desc = "Write a .meta.json sidecar file. Usage: --hook sidecar"
    stage = "file"
    category = "metadata"

    def run(self, entries):
        for mod, entry in entries:
            if entry.get("status") != 0:
                continue

            filepath = entry.get("dst_fn")
            if not filepath or not os.path.exists(filepath):
                continue

            meta_fn = filepath + ".meta.json"
            meta_data = {
                "source_module": mod.name,
                "source_url": entry.get("url"),
                "download_date": datetime.now().isoformat(),
                "original_filename": os.path.basename(filepath),
                "tags": getattr(mod, "tags", []),
                "extra": {
                    k: v
                    for k, v in entry.items()
                    if k not in ["url", "dst_fn", "status", "stream"]
                },
            }

            try:
                with open(meta_fn, "w") as f:
                    json.dump(meta_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to write sidecar for {filepath}: {e}")

        return entries
