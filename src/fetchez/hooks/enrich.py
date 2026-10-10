#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.enrich
~~~~~~~~~~~~~

Enrich the entry with some metadata

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import mimetypes
from pathlib import Path
from datetime import datetime

from fetchez.hooks import FetchHook
from fetchez.datatypes.detectors import detect_entry

logger = logging.getLogger(__name__)


class MetadataEnrich(FetchHook):
    """Enrich entries with filesystem metadata and optional data-type detection."""

    name = "enrich"
    meta_desc = "Add filesystem metadata and optionally detect data types."
    meta_stage = "file"
    meta_category = "metadata"

    def __init__(
        self,
        detect_data_type=False,
        overwrite_data_type=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.detect_data_type = detect_data_type
        self.overwrite_data_type = overwrite_data_type

    def run(self, entries):
        for _mod, entry in entries:
            filepath = entry.get("dst_fn")

            if entry.get("status") != 0 or not filepath or not Path(filepath).is_file():
                continue

            try:
                stat = Path(filepath).stat()

                entry["created_at"] = datetime.fromtimestamp(stat.st_ctime).isoformat()

                entry["modified_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat()

                mime, _ = mimetypes.guess_type(filepath)
                entry["mime_type"] = mime or "application/octet-stream"

                if self.detect_data_type:
                    detect_entry(
                        entry,
                        overwrite=self.overwrite_data_type,
                    )

            except Exception as exc:
                logger.warning(
                    "Metadata enrichment failed for %s: %s",
                    filepath,
                    exc,
                )

        return entries
