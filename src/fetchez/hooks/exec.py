#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.hooks.exec
~~~~~~~~~~~~~~~~~~~~~~

Run external programs against Fetchez entries, optionally publishing outputs.

Single-file outputs use ``fetchez.output`` helpers (or the equivalent location
in the host Fetchez package). Command execution never implicitly invokes a shell.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os
from pathlib import Path
import shlex
import string
import subprocess

from fetchez.hooks import FetchHook
from fetchez.utils import output_name, atomic_output

logger = logging.getLogger(__name__)

_FIELDS = {"file", "url", "dir", "filename", "name", "stem", "output"}


def _format_arg(template, fields):
    """Format one argument, rejecting unknown fields and format expressions."""
    formatter = string.Formatter()
    for _, field, spec, conversion in formatter.parse(str(template)):
        if field is not None and (field not in _FIELDS or spec or conversion):
            raise ValueError(f"Unsupported Exec command placeholder: {field!r}")
    return str(template).format_map(fields)


class Exec(FetchHook):
    """Execute a command for each entry, optionally publishing a new file.

    Without ``output``, this is a side-effect hook: the entry is not changed.
    With ``output`` (a dictionary), ``{output}`` designates a staged filename,
    published after the command succeeds. A declared output is registered as
    an artifact, and becomes dst_fn unless update_entry=False.

    ``cmd`` can be a list of argv templates (recommended) or a shell-like
    string. Shell operators are not interpreted; use explicit subprocesses
    or a script when shell functionality is needed.
    """

    name = "exec"
    meta_desc = "Execute external commands; optionally publish resulting files."
    meta_stage = "file"
    meta_category = "file-op"
    meta_effects = ["consumes-artifact"]

    def __init__(
        self,
        cmd=None,
        output=None,
        output_path=None,
        suffix=None,
        extension=None,
        update_entry=None,
        artifact_id=None,
        timeout=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.cmd = cmd
        if output is not None and not isinstance(output, dict):
            raise TypeError(
                "output must be a mapping (for example: {'suffix': '_cog'})"
            )
        if output is not None and any(
            x is not None for x in (output_path, suffix, extension)
        ):
            raise ValueError(
                "Specify output naming in 'output' OR legacy keyword arguments"
            )
        if output is None and any(
            x is not None for x in (output_path, suffix, extension)
        ):
            output = {
                "output_path": output_path,
                "suffix": suffix,
                "extension": extension,
            }
        self.output = dict(output) if output is not None else None
        if self.output is not None:
            allowed = {
                "output_path",
                "suffix",
                "extension",
                "artifact_id",
                "update_entry",
                "overwrite",
            }
            extras = set(self.output) - allowed
            if extras:
                raise ValueError(f"Unsupported Exec output options: {sorted(extras)}")
        self.update_entry = update_entry
        self.artifact_id = artifact_id
        self.timeout = timeout

    def _argv(self, fields):
        if isinstance(self.cmd, str):
            # Parse before formatting to keep a substituted path with spaces in
            # one argv token when a template is quoted as one token.
            templates = shlex.split(self.cmd)
        elif isinstance(self.cmd, (list, tuple)):
            templates = self.cmd
        else:
            raise ValueError("Exec cmd must be a string or a sequence of arguments")
        if not templates:
            raise ValueError("Exec cmd is empty")
        return [_format_arg(item, fields) for item in templates]

    def run(self, entries):
        result = list(entries)
        if not self.cmd:
            return result

        eligible = [(mod, e) for mod, e in result if e.get("status") in (None, 0)]
        if self.output is not None:
            paths = []
            for index, (_, entry) in enumerate(eligible):
                if not entry.get("dst_fn"):
                    raise ValueError("Exec transformation requires entry['dst_fn']")
                cfg = self.output
                path = output_name(
                    entry,
                    output_path=cfg.get("output_path"),
                    suffix=cfg.get("suffix", "_processed"),
                    extension=cfg.get("extension"),
                    index=index,
                    total=len(eligible),
                )
                if path == Path(entry["dst_fn"]).resolve():
                    raise ValueError("Exec output must not overwrite its input")
                paths.append(path)
            if len(set(paths)) != len(paths):
                raise ValueError("Exec output paths collide across entries")
        else:
            paths = [None] * len(eligible)

        for (_mod, entry), destination in zip(eligible, paths, strict=True):
            if not entry.get("dst_fn"):
                raise ValueError("Exec requires entry['dst_fn']")
            source = Path(os.fspath(entry["dst_fn"]))
            fields = dict(
                file=str(source),
                url=str(entry.get("url") or ""),
                dir=str(source.parent),
                filename=source.name,
                name=source.stem,
                stem=source.stem,
                output="",
            )
            if destination is None:
                command = self._argv(fields)
                logger.info("Exec: %s", shlex.join(command))
                subprocess.run(command, check=True, timeout=self.timeout)
                continue

            cfg = self.output
            with atomic_output(
                destination, overwrite=cfg.get("overwrite", True)
            ) as temporary:
                fields["output"] = str(temporary)
                command = self._argv(fields)
                # Do not silently publish the empty mkstemp placeholder if the
                # command did not actually declare the output argument.
                if not any(
                    "{output}" in str(part)
                    for part in (
                        shlex.split(self.cmd) if isinstance(self.cmd, str) else self.cmd
                    )
                ):
                    raise ValueError("Exec transformation cmd must contain {output}")
                temporary.unlink()  # Let output program create its own file.
                logger.info("Exec: %s", shlex.join(command))
                subprocess.run(command, check=True, timeout=self.timeout)
                if not temporary.is_file():
                    raise FileNotFoundError(f"Exec did not produce {temporary}")

            artifact_id = cfg.get("artifact_id") or self.artifact_id or self.name
            entry.setdefault("artifacts", {})[artifact_id] = destination
            should_update = cfg.get("update_entry", self.update_entry)
            if should_update is None or should_update:
                entry["dst_fn"] = destination

        return result
