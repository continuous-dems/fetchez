#!/usr/bin/env python

"""
fetchez.hooks.checksum
~~~~~~~~~~~~~

Calculate the checksum of each result entry.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import hashlib
import logging
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Checksum(FetchHook):
    """Calculates file checksums immediately after download.

    Adds '{algo}_hash' and 'local_size' to the result dictionary.

    Usage: --hook checksum:algo=sha256
    """

    name = "checksum"
    meta_desc = "Calculate file checksums (md5/sha1/sha256)."
    meta_stage = "file"
    meta_category = "metadata"
    meta_requires = "file"

    def __init__(self, algo="md5", **kwargs):
        super().__init__(**kwargs)
        self.algo = algo.lower()
        if self.algo not in hashlib.algorithms_available:
            logger.warning(f"Checksum algo '{self.algo}' not found. Defaulting to md5.")
            self.algo = "md5"

    def run(self, entries):
        for _mod, entry in entries:
            filepath = entry.get("dst_fn")

            if entry.get("status") != 0 or not Path(filepath).exists():
                entry[f"{self.algo}_hash"] = None
                entry["local_size"] = 0
                continue

            try:
                hasher = hashlib.new(self.algo)
                size = 0
                with open(filepath, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                        size += len(chunk)

                entry[f"{self.algo}_hash"] = hasher.hexdigest()
                entry["local_size"] = size

                remote_size = entry.get("remote_size")
                if remote_size:
                    try:
                        if int(remote_size) != size:
                            logger.warning(
                                f"Size mismatch for {filepath}: {size} != {remote_size}"
                            )
                            entry["verification"] = "failed"
                        else:
                            entry["verification"] = "passed"
                    except ValueError:
                        pass  # remote_size might not be an int

            except Exception as e:
                logger.warning(f"Checksum failed for {filepath}: {e}")

        return entries
