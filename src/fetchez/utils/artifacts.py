#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.utils.artifacts
~~~~~~~~~~~~~~~~~~~~~~~

Compatibility helpers for entry-level and execution-scoped artifacts.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path


def artifact_owner(module):
    """Use the recipe occurrence ID where available, otherwise its module name."""
    return getattr(module, "instance_id", None) or getattr(module, "name", None)


def publish(hook, module, entry, name, path):
    """Keep the legacy entry record and publish to the optional run catalog."""
    entry.setdefault("artifacts", {})[name] = path
    context = getattr(hook, "context", None)
    catalog = getattr(context, "artifacts", None)
    if catalog is not None:
        catalog.publish(name, path, owner=artifact_owner(module))


def paths(value):
    """Interpret legacy single-path and multiple-path artifact values."""
    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        return (str(value),)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item is not None)
    return ()


def selected_files(hook, entries, matches):
    """Find existing input paths; retain dst_fn-only default copy semantics.

    When match patterns are supplied, search both active entry artifacts and
    the execution catalog. Matches refer to path substrings (legacy behavior).
    """
    chosen = {}

    if matches:
        for _module, entry in entries:
            for value in (entry.get("artifacts") or {}).values():
                for path in paths(value):
                    if (
                        any(pattern in path for pattern in matches)
                        and Path(path).is_file()
                    ):
                        chosen[path] = None
        catalog = getattr(getattr(hook, "context", None), "artifacts", None)
        if catalog is not None:
            for artifact in catalog.find():
                path = artifact.path
                if any(pattern in path for pattern in matches) and Path(path).is_file():
                    chosen[path] = None
    else:
        for _module, entry in entries:
            path = entry.get("dst_fn")
            if path is not None and Path(path).is_file():
                chosen[str(path)] = None

    return list(chosen)
