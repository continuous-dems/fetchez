#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.file_ops
~~~~~~~~~~~~~

This holds the file operation related fetchez hooks.
These are default standard hooks.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import zipfile
import subprocess
import shlex
import logging
from . import FetchHook

logger = logging.getLogger(__name__)


class Flatten(FetchHook):
    """Flattens output directory structure.

    Args:
        mode (str):
            'module' (default) -> outdir/module/file.ext (Flattens subdirs INSIDE module)
            'root'             -> outdir/file.ext (Removes module folder)
            'cwd'              -> ./file.ext (Ignores outdir completely)
    """

    name = "flatten"
    stage = "pre"
    category = "file-op"

    def __init__(self, mode="module", **kwargs):
        super().__init__(**kwargs)
        self.mode = mode.lower()

    def run(self, entries):
        for mod, entry in entries:
            current_path = entry.get("dst_fn")
            if not current_path:
                continue

            filename = os.path.basename(current_path)
            if self.mode == "cwd":
                new_dir = os.getcwd()

            elif self.mode == "root":
                new_dir = mod.outdir if mod.outdir else os.getcwd()

            elif self.mode == "module":
                new_dir = mod._outdir

            entry["dst_fn"] = os.path.join(new_dir, filename)

        return entries


class Unzip(FetchHook):
    """Automatically unzip files after download."""

    # Registry Metadata
    name = "unzip"
    desc = "Extract .zip archives. Usage: --hook unzip:remove=true:overwrite=false"
    stage = "file"
    category = "file-op"

    def __init__(self, remove=False, overwrite=False, **kwargs):
        """
        Args:
            remove (bool): Delete the original .zip file after extraction.
            overwrite (bool): Overwrite existing files.
        """

        super().__init__(**kwargs)
        self.remove = remove
        self.overwrite = overwrite

    def run(self, entries):
        out_entries = []
        for mod, entry in entries:
            zip_path = entry.get("dst_fn")
            status = entry.get("status")

            if status != 0 or not zip_path.lower().endswith(".zip"):
                out_entries.append((mod, entry))
                continue

            extract_dir = os.path.dirname(zip_path)

            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    files_to_extract = [n for n in z.namelist() if not n.endswith("/")]

                    if not self.overwrite:
                        if all(
                            os.path.exists(os.path.join(extract_dir, f))
                            for f in files_to_extract
                        ):
                            logger.info(
                                f"Skipping unzip (files exist): {os.path.basename(zip_path)}"
                            )
                            out_entries.extend(
                                [
                                    (
                                        mod,
                                        {
                                            **entry,
                                            "dst_fn": os.path.join(extract_dir, f),
                                            "status": 0,
                                        },
                                    )
                                    for f in files_to_extract
                                ]
                            )
                            continue

                    z.extractall(extract_dir)

                    for fname in files_to_extract:
                        full_path = os.path.join(extract_dir, fname)
                        out_entries.append(
                            (
                                mod,
                                {
                                    **entry,
                                    "dst_fn": full_path,
                                    "status": 0,
                                    "src_fn": zip_path,
                                },
                            )
                        )

                if self.remove:
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass

            except Exception as e:
                logger.error(f"Unzip failed for {zip_path}: {e}")
                out_entries.append((mod, entry))

        return out_entries


class Exec(FetchHook):
    """Run an arbitrary shell command on each file.
    Template variables: {file}, {url}, {dir}, {name}

    Usage: --hook exec:cmd="gdal_translate -of COG {file} {dir}/{name}_cog.tif"
    """

    name = "exec"
    desc = "Run shell command on file. Usage: --hook exec:cmd='echo {file}'"
    stage = "file"
    category = "pipeline"

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
