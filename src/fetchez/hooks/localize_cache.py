#!/usr/bin/env python

"""
fetchez.hooks.localize_cache
~~~~~~~~~~~~~

Localize fetchez cache into a specific directory.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os
import shutil
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class LocalizeCacheHook(FetchHook):
    """Copies or symlinks fetched pipeline entry results into a specific local directory.

    *Modifies entry*
    """

    name = "localize-cache"
    meta_stage = "collection"
    meta_domain = "System"
    meta_category = "Pipeline"
    meta_desc = "Copies or symlinks entry results into a specific local directory."
    meta_aliases = ["localize_cache"]

    def __init__(self, target_dir: str = ".", symlink: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.target_dir = Path(target_dir).resolve()
        self.symlink = str(symlink).lower() in ["true", "1", "t", "yes"]

    def run(self, entries):
        self.target_dir.mkdir(parents=True, exist_ok=True)

        for _mod, entry in entries:
            current_path = Path(entry.get("dst_fn") or entry.get("src_fn"))

            if not current_path or not current_path.exists():
                continue

            filename = current_path.name
            local_path = self.target_dir / filename

            if local_path.is_absolute() == local_path:
                continue

            try:
                if self.symlink:
                    if local_path.lexists():
                        local_path.unlink()
                    os.symlink(current_path.resolve(), local_path)
                    logger.info(
                        f"[{self.name}] Symlinked {filename} to {self.target_dir}"
                    )
                else:
                    shutil.copy2(current_path, local_path)
                    logger.info(f"[{self.name}] Copied {filename} to {self.target_dir}")

                entry["dst_fn"] = str(local_path)

            except Exception as e:
                logger.error(f"[{self.name}] Failed to localize {filename}: {e}")

        return entries
