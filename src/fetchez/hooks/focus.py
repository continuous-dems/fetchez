#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.focus
~~~~~~~~~~~~~~~~~~~

Pipeline control hooks for artifact focus.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez.hooks import FetchHook
from fetchez.utils.artifacts import artifact_owner, paths

logger = logging.getLogger(__name__)


class FocusSink(FetchHook):
    """Shrinks the pipeline entries down to the output of a specific Sink/Hook.
    Subsequent Post-Hooks will only act on these generated artifacts.

    The target hook must adhere to the 'Artifact Protocol' by registering
    its outputs in `entry['artifacts'][hook_name] = output_path`.

    That output_path then becomes the entry['dst_fn']

    Usage:
      --hook focus-sink:target=blended_checkpoint
    """

    name = "focus-sink"
    meta_desc = "Focus the pipeline to an 'artifact'"
    meta_stage = "collection"  # post
    meta_category = "pipeline"
    meta_aliases = ["focus_sink"]
    meta_effects = ["modifies-entries", "modifies-artifact", "filters-entries"]

    def __init__(self, target=None, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    def run(self, entries):
        if not self.target:
            logger.warning("No target specified. Ignoring.")
            return entries

        new_entries = []
        seen_paths = set()
        owners = {}
        for mod, _entry in entries:
            owner = artifact_owner(mod)
            if owner is not None:
                owners.setdefault(owner, mod)

        # A recipe plan can resolve producers even after their source entries
        # have been removed from the active collection.
        plan = getattr(getattr(self, "context", None), "plan", None)
        plan_modules = getattr(plan, "modules_by_id", None)
        if isinstance(plan_modules, dict):
            for owner, module in plan_modules.items():
                owners.setdefault(owner, module)

        def append(mod, path, artifacts=None):
            path = str(path)
            if path in seen_paths:
                return
            seen_paths.add(path)
            focused = {
                "url": f"file://{path}",
                "dst_fn": path,
                "status": 0,
                "data_type": f"{self.target}_artifact",
                "artifacts": artifacts
                if artifacts is not None
                else {self.target: path},
            }
            new_entries.append((mod, focused))

        # Retain entry-level ownership and metadata for legacy producers.
        for mod, entry in entries:
            artifacts = entry.get("artifacts") or {}
            for path in paths(artifacts.get(self.target)):
                append(mod, path, artifacts)

        # Catalog artifacts survive filtering or replacement of entry lists.
        catalog = getattr(getattr(self, "context", None), "artifacts", None)
        if catalog is not None:
            for artifact in catalog.find(self.target):
                if artifact.path in seen_paths:
                    continue
                mod = owners.get(artifact.owner) if artifact.owner else None
                if mod is None and artifact.owner is None and len(owners) == 1:
                    mod = next(iter(owners.values()))
                if mod is None:
                    logger.warning(
                        "Cannot focus catalog artifact %r (%s): unresolved module owner %r",
                        artifact.name,
                        artifact.path,
                        artifact.owner,
                    )
                    continue
                append(mod, artifact.path)

        if not new_entries:
            logger.warning(
                "Artifact target %r was not found with resolvable ownership; "
                "passing original entries onward.",
                self.target,
            )
            return entries

        logger.debug(
            "Shrunk pipeline to %d %r artifacts.", len(new_entries), self.target
        )
        return new_entries


class StashEntries(FetchHook):
    name = "stash-entries"
    meta_desc = "Save the current pipeline state for branching"
    meta_stage = "collection"
    meta_stages = ("manifest", "collection", "finalize")
    meta_category = "pipeline"
    meta_aliases = ["stash_entries"]
    meta_effects = ["consumes-entries", "modifies-entries"]

    def __init__(self, key="default", **kwargs):
        super().__init__(**kwargs)
        self.key = key

    def run(self, entries):
        self.context.stashes.save(self.key, entries)
        logger.debug(f"Stashed {len(entries)} entries under key '{self.key}'.")
        return entries


class RestoreEntries(FetchHook):
    name = "restore-entries"
    meta_desc = "Restore a previously saved pipeline stash"
    meta_stage = "collection"
    meta_stages = ("manifest", "collection", "finalize")
    meta_category = "pipeline"
    meta_aliases = ["restore_entries"]
    meta_effects = ["modifies-entries", "creates-entries"]

    def __init__(self, key="default", merge=False, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.merge = str(merge).lower() in ("true", "1", "t", "yes")

    def run(self, entries):
        if not self.context.stashes.has(self.key):
            logger.warning(
                "Entry stash %r not found. Ignoring.",
                self.key,
            )
            return entries

        restored = self.context.stashes.get(self.key)

        if self.merge:
            logger.debug(
                f"Merged {len(restored)} stashed entries from '{self.key}' into pipeline."
            )
            return entries + restored

        logger.debug(f"Restored pipeline to {len(restored)} entries from '{self.key}'.")
        return restored
