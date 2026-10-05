#!/usr/bin/env python

"""
fetchez.hooks.enrich
~~~~~~~~~~~~~

Enrich the entry with some metadata

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import mimetypes
from datetime import datetime
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class MetadataEnrich(FetchHook):
    """Adds filesystem timestamps and mime-types to the result.

    Usage: --hook enrich
    """

    name = "enrich"
    meta_desc = "Add file timestamps and mime-types to metadata."
    meta_stage = "file"
    meta_category = "metadata"

    def run(self, entries):
        for _mod, entry in entries:
            filepath = entry.get("dst_fn")

            if entry.get("status") != 0 or not Path(filepath).exists():
                continue

            try:
                stat = Path(filepath).stat()
                entry["created_at"] = datetime.fromtimestamp(stat.st_ctime).isoformat()
                entry["modified_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat()

                mime, _ = mimetypes.guess_type(filepath)
                entry["mime_type"] = mime or "application/octet-stream"

            except Exception as e:
                logger.warning(f"Metadata enrichment failed for {filepath}: {e}")

        return entries
