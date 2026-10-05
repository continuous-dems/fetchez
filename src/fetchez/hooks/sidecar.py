#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.sidecar
~~~~~~~~~~~~~

Generates a 'sidecar' metadata file for each entry

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from fetchez.hooks import FetchHook
from fetchez import cli

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Genearte a sidecar metdata file",
)
class Sidecar(FetchHook):
    """Write a metadata sidecar file (.meta.json) for every download.

    Useful for data provenance (tracking source URLs and dates).
    """

    name = "sidecar"
    meta_desc = "Write a .meta.json sidecar file."
    meta_stage = "file"
    meta_category = "metadata"

    def run(self, entries):
        for mod, entry in entries:
            if entry.get("status") != 0:
                continue

            filepath = entry.get("dst_fn")
            if not filepath or not Path(filepath).exists():
                continue

            meta_fn = filepath + ".meta.json"
            meta_data = {
                "source_module": mod.name,
                "source_url": entry.get("url"),
                "download_date": datetime.now().isoformat(),
                "original_filename": Path(filepath).name,
                "tags": getattr(mod, "tags", []),
                "extra": {
                    key: val
                    for key, val in entry.items()
                    if key not in ["url", "dst_fn", "status", "stream"]
                },
            }

            try:
                with open(meta_fn, "w") as f:
                    json.dump(meta_data, f, indent=2)

                # Add sidecar as an artifact to the entry
                entry.setdefault("artifacts", {})[self.name] = meta_fn
            except Exception as e:
                logger.warning(f"Failed to write sidecar for {filepath}: {e}")

        return entries
