#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.output
~~~~~~~~~~~~~~~~

Utility functions for general output operations.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import tempfile
from pathlib import Path

from contextlib import contextmanager
import string


logger = logging.getLogger(__name__)


_FIELDS = {"stem", "name", "suffix", "index"}


def output_name(
    entry, *, output_path=None, suffix="_processed", extension=None, index=0, total=1
):
    """Return destination Path for an entry, without creating it.

    output_path: None (beside entry dst_fn), directory (existing or trailing
    separator), explicit filename (only for one entry), or a template using
    {stem}, {name}, {suffix}, and {index}.
    extension: optional output extension, e.g. '.tif'. Defaults to source extension.

    For a not-yet-existing directory, use a trailing '/' or a template such as
    'processed/{stem}_filtered.tif' to disambiguate it from a filename.
    """
    source = Path(os.fspath(entry.get("dst_fn") or "out"))
    ext = source.suffix if extension is None else str(extension)
    if ext and not ext.startswith("."):
        ext = "." + ext
    filename = f"{source.stem}{suffix}{ext}"

    if output_path is None:
        return source.with_name(filename).resolve()

    value = os.fspath(output_path)
    fields = set()
    try:
        for _, field, spec, conv in string.Formatter().parse(value):
            if field is not None:
                if field not in _FIELDS or spec or conv:
                    raise ValueError(f"Unsupported output_path field: {field!r}")
                fields.add(field)
    except ValueError as exc:
        raise ValueError(f"Invalid output_path template {value!r}: {exc}") from exc

    if fields:
        if total > 1 and not ({"stem", "name", "index"} & fields):
            raise ValueError(
                "Multi-entry output template needs {stem}, {name}, or {index}"
            )
        resolved = value.format(
            stem=source.stem, name=source.name, suffix=suffix, index=index
        )
        return Path(resolved).resolve()

    target = Path(value)
    if value.endswith((os.sep, "/")) or target.is_dir():
        return (target / filename).resolve()

    if total > 1:
        raise ValueError(
            "Explicit output filename requires one entry; use a directory or template"
        )
    return target.resolve()


@contextmanager
def atomic_output(destination, *, suffix=None, overwrite=True):
    """Yield temporary Path on same filesystem; publish after successful exit.

    The caller must fully close any writer before leaving the block. On error,
    the temporary file is removed and an existing destination remains intact.
    This is atomic replacement, not a durable transaction or multi-file commit.
    """
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and destination.exists():
        raise FileExistsError(destination)

    fd, filename = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=suffix or destination.suffix,
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(filename)
    try:
        yield temporary
        if not temporary.is_file():
            raise FileNotFoundError(
                f"Output writer removed its temporary file: {temporary}"
            )
        if not overwrite and destination.exists():
            raise FileExistsError(destination)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
