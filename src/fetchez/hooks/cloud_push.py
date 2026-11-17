#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.hooks.cloud_push
~~~~~~~~~~~~~~~~~~~~~~~~

Pushes resulting artifacts to remote cloud storage.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import subprocess
from pathlib import Path
from fetchez.hooks import FetchHook
from fetchez.utils.artifacts import selected_files

logger = logging.getLogger(__name__)


class CloudPushHook(FetchHook):
    """Pushes resulting artifacts to remote cloud storage.

    Supports both 'rclone' (best for GDrive/OneDrive) and 'fsspec' (best for S3/Blob).

    Usage:
      --hook cloud_push:remote_dir="gdrive:Fiji_Workshop/",backend="rclone",match="dem.tif"
      --hook cloud_push:remote_dir="s3://my-bucket/dems",backend="fsspec"
    """

    name = "cloud_push"
    meta_stage = "collection"
    meta_category = "pipeline"
    meta_desc = (
        "Pushes resulting artifacts to remote cloud storage using rclone or fsspec."
    )
    meta_aliases = ["cloud-push", "push_artifact"]
    meta_effects = ["modifies-artifact", "consumes-artifact"]

    def __init__(self, remote_dir=None, match=None, backend="rclone", **kwargs):
        super().__init__(**kwargs)
        self.remote_dir = remote_dir
        self.backend = str(backend).lower()

        # Parse match strings identically to copy_artifact
        if isinstance(match, str):
            self.matches = [m.strip() for m in match.split("/")]
        elif isinstance(match, list):
            self.matches = match
        else:
            self.matches = []

    def run(self, entries):
        if not self.remote_dir:
            logger.error(f"[{self.name}] A 'remote_dir' is required.")
            return entries

        # Pre-flight check for fsspec backend
        fs = None
        if self.backend == "fsspec":
            try:
                import fsspec

                fs, _ = fsspec.core.url_to_fs(self.remote_dir)
            except ImportError:
                logger.error(
                    f"[{self.name}] The 'fsspec' library is required for the fsspec backend.",
                )
                return entries

        files_to_copy = selected_files(self, entries, self.matches)
        for fpath in files_to_copy:
            logger.info(
                f"[{self.name}] Uploading {Path(fpath).name} via {self.backend} -> {self.remote_dir}",
            )

            if self.backend == "rclone":
                try:
                    # rclone natively handles copying a file to a remote directory prefix
                    subprocess.run(
                        ["rclone", "copy", fpath, self.remote_dir],
                        check=True,
                    )
                except FileNotFoundError:
                    logger.error(
                        f"[{self.name}] 'rclone' executable not found. Is it installed and on your PATH?",
                    )
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"[{self.name}] rclone transfer failed on {fpath}: {e}",
                    )

            elif self.backend == "fsspec":
                try:
                    remote_dest = f"{self.remote_dir.rstrip('/')}/{Path(fpath).name}"
                    fs.put(fpath, remote_dest)
                except Exception as e:
                    logger.error(
                        f"[{self.name}] fsspec transfer failed on {fpath}: {e}",
                    )

        return entries
