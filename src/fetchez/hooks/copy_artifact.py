#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.hooks.copy_artifact
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copy a registrered entry artifact to a new location.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import shutil
import logging
from pathlib import Path

from fetchez.hooks import FetchHook
from fetchez.utils.artifacts import selected_files

logger = logging.getLogger(__name__)


class CopyArtifactHook(FetchHook):
    """Copies resulting artifacts to a target directory. Useful for batch collating.

    *Does not modify entry*

    Usage:
      --hook copy-artifact:target_dir="../_collate",match="dem.tif/hillshade.tif"
    """

    name = "copy-artifact"
    meta_stage = "collection"
    meta_category = "file-op"
    meta_desc = (
        "Copies resulting artifacts to a target directory. Useful for batch collating."
    )
    meta_aliases = ["copy_artifact"]
    meta_effects = ["modifies-artifact"]

    def __init__(self, target_dir="../_collate", match=None, **kwargs):
        super().__init__(**kwargs)
        self.target_dir = Path(target_dir).resolve()

        if isinstance(match, str):
            self.matches = [m.strip() for m in match.split("/")]
        elif isinstance(match, list):
            self.matches = match
        else:
            self.matches = []

    def run(self, entries):
        target_path = Path(self.target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        files_to_copy = selected_files(self, entries, self.matches)
        for fpath in files_to_copy:
            path_to_copy = Path(fpath)
            destination_path = target_path / path_to_copy.name

            try:
                shutil.copy2(fpath, destination_path)
                logger.info(
                    f"[{self.name}] Collating {path_to_copy.name} -> {destination_path}"
                )
            except Exception as e:
                logger.error(f"[{self.name}] Failed to copy {path_to_copy}: {e}")

        return entries
