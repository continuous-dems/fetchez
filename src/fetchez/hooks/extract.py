#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.extract
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Extract and decompress archive files safely.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path

from fetchez.hooks import FetchHook
from fetchez.utils import p_f_extract

logger = logging.getLogger(__name__)


class Extract(FetchHook):
    """Extract or decompress archive files."""

    name = "extract"
    meta_desc = "Extract .zip, .tar, .tar.gz, .tgz, and .gz files."
    meta_stage = "file"
    meta_category = "file-op"
    # meta_aliases = ["unzip"]

    def __init__(
        self,
        remove: bool = False,
        overwrite: bool = False,
        members: list[str] | None = None,
        **kwargs,
    ):
        """Extract and/or decompress files.

        Args:
            remove: Delete the original archive after successful extraction.
            overwrite: Replace existing extracted files.
            members: Optional archive member/name patterns to extract.
        """
        super().__init__(**kwargs)
        self.remove = remove
        self.overwrite = overwrite
        self.members = members

    def run(self, entries):
        out_entries = []

        for mod, entry in entries:
            file_path = Path(entry.get("dst_fn", ""))
            status = entry.get("status")

            if (status is not None and status != 0) or not file_path:
                out_entries.append((mod, entry))
                continue

            try:
                extracted = p_f_extract(
                    file_path,
                    outdir=file_path.parent,
                    members=self.members,
                    overwrite=self.overwrite,
                )

            except ValueError:
                # Not an archive format handled by this hook.
                out_entries.append((mod, entry))
                continue

            except Exception as exc:
                logger.error(
                    "Extraction failed for %s: %s",
                    file_path,
                    exc,
                )
                out_entries.append((mod, entry))
                continue

            for extracted_path in extracted:
                out_entries.append(
                    (
                        mod,
                        {
                            **entry,
                            "dst_fn": str(extracted_path),
                            "src_fn": str(file_path),
                            "status": 0,
                        },
                    )
                )

            if self.remove:
                try:
                    file_path.unlink()
                except OSError:
                    pass

        return out_entries
