#!/usr/bin/env python

"""
fetchez.hooks..exec
~~~~~~~~~~~~~

Run subprocess on the entry fn; using format templates.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import shlex
import subprocess
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Exec(FetchHook):
    """Run an arbitrary shell command on each file.

    Template variables: {file}, {url}, {dir}, {name}

    Usage: --hook exec:cmd="gdal_translate -of COG {file} {dir}/{name}_cog.tif"
    """

    name = "exec"
    meta_desc = "Run shell command on file."
    meta_stage = "file"
    meta_category = "file-op"

    def __init__(self, cmd=None, **kwargs):
        super().__init__(**kwargs)
        self.cmd = cmd

    def run(self, entries):
        if self.cmd:
            for _mod, entry in entries:
                if entry.get("status") != 0:
                    continue

                filepath = Path(entry.get("dst_fn"))
                dirname = filepath.parent
                filename = filepath.name
                name_only = filepath.with_suffix("").name
                command_str = self.cmd.format(
                    file=filepath,
                    url=entry.get("url"),
                    dir=dirname,
                    filename=filename,
                    name=name_only,
                )

                try:
                    logger.info(f"Exec: {command_str}")
                    subprocess.run(shlex.split(command_str), check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Exec command failed: {e}")

        return entries
