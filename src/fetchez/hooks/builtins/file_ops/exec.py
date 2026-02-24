#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.exec
~~~~~~~~~~~~~

Run subprocess on the entry fn

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import subprocess
import shlex
import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Exec(FetchHook):
    """Run an arbitrary shell command on each file.
    Template variables: {file}, {url}, {dir}, {name}

    Usage: --hook exec:cmd="gdal_translate -of COG {file} {dir}/{name}_cog.tif"
    """

    name = "exec"
    desc = "Run shell command on file. Usage: --hook exec:cmd='echo {file}'"
    stage = "file"
    category = "file-op"

    def __init__(self, cmd=None, **kwargs):
        super().__init__(**kwargs)
        self.cmd = cmd

    def run(self, entries):
        if not self.cmd:
            return entries

        for mod, entry in entries:
            if entry.get("status") != 0:
                continue

            filepath = os.path.abspath(entry.get("dst_fn"))
            dirname = os.path.dirname(filepath)
            filename = os.path.basename(filepath)
            name_only = os.path.splitext(filename)[0]
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
