#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.files
~~~~~~~~~~~~~~~~

Utility functions for file ops.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from .misc import str_or


logger = logging.getLogger(__name__)


def fn_url_p(fn: str) -> bool:
    """Check if fn is a URL."""

    url_sw = ["http://", "https://", "ftp://", "ftps://", "/vsicurl"]
    if str_or(fn):
        try:
            for u in url_sw:
                if fn.startswith(u):
                    return True
        except Exception as e:
            logger.debug(f"Could not parse url {fn}: {e}")
            return False
    return False


def remove_glob2(*args: str) -> int:
    """Glob paths and recursively delete matching files and directories."""

    for glob_pattern in args:
        try:
            # Match top-level paths based on the provided glob pattern
            # Uses Path(".") as the base directory anchor for the pattern
            if Path(glob_pattern).is_absolute():
                Path(glob_pattern).unlink(missing_ok=True)
            else:
                for path in Path(".").glob(glob_pattern):
                    if not path.exists():
                        continue
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Could not remove path with glob pattern {glob_pattern}: {e}")
            return -1
    return 0


remove_glob = remove_glob2


def make_temp_fn(basename: str, temp_dir: Optional[str] = None) -> str:
    """Generate a temporary filename."""

    basename_path = Path(basename)
    prefix = basename_path.stem
    suffix = basename_path.suffix
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=f"{prefix}_", dir=temp_dir)
    os.close(fd)
    return path
