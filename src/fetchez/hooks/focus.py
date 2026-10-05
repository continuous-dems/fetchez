#!/usr/bin/env python

"""
fetchez.hooks.focus
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pipeline control hooks for artifact focus.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.hooks import FetchHook

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

    def __init__(self, target=None, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    def run(self, entries):
        if not self.target:
            logger.warning("No target specified. Ignoring.")
            return entries

        new_entries = []
        seen_paths = set()
        found_target = False

        for mod, entry in entries:
            artifacts = entry.get("artifacts", {})

            if self.target in artifacts:
                found_target = True

                # Artifacts can be a single path or a list of paths
                artifact_paths = artifacts[self.target]
                if isinstance(artifact_paths, str):
                    artifact_paths = [artifact_paths]

                for path in artifact_paths:
                    if path not in seen_paths:
                        seen_paths.add(path)

                        focused_entry = {
                            "url": f"file://{path}",
                            "dst_fn": path,
                            "status": 0,
                            "data_type": f"{self.target}_artifact",
                            "artifacts": artifacts,
                        }
                        new_entries.append((mod, focused_entry))

        if not found_target:
            logger.warning(
                f"Artifact target '{self.target}' was not found in any pipeline entries! "
                f"Ignoring focus request and passing original entry onward."
            )
            return entries

        logger.debug(
            f"Shrunk pipeline to {len(new_entries)} '{self.target}' artifacts."
        )
        return new_entries


class StashEntries(FetchHook):
    """Saves the current pipeline entries state to memory for later restoration."""

    name = "stash-entries"
    meta_desc = "Save the current pipeline state for branching"
    meta_stage = "post"
    meta_category = "pipeline"
    meta_aliases = ["stash_entries"]

    def __init__(self, key="default", **kwargs):
        super().__init__(**kwargs)
        self.key = key

    def run(self, entries):
        if not entries:
            return entries

        # We store the stash dictionary on the first module in the pipeline
        first_mod = entries[0][0]
        if not hasattr(first_mod, "_pipeline_stash"):
            first_mod._pipeline_stash = {}

        # Save a shallow copy of the entries list
        first_mod._pipeline_stash[self.key] = list(entries)
        logger.debug(f"Stashed {len(entries)} entries under key '{self.key}'.")

        return entries


class RestoreEntries(FetchHook):
    """Restores previously stashed pipeline entries, allowing pipeline branching."""

    name = "restore-entries"
    meta_desc = "Restore a previously saved pipeline stash"
    meta_stage = "post"
    meta_category = "pipeline"
    meta_aliases = ["restore_entries"]

    def __init__(self, key="default", merge=False, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.merge = str(merge).lower() in ["true", "1", "t", "yes"]

    def run(self, entries):
        # Scan the current modules to find the stashed dictionary
        stashed_entries = None
        for mod, _ in entries:
            if hasattr(mod, "_pipeline_stash") and self.key in mod._pipeline_stash:
                stashed_entries = mod._pipeline_stash[self.key]
                break

        if stashed_entries is None:
            logger.warning(
                f"Could not find stashed entries with key '{self.key}'. Ignoring."
            )
            return entries

        if self.merge:
            logger.debug(
                f"Merged {len(stashed_entries)} stashed entries from '{self.key}' into pipeline."
            )
            return entries + stashed_entries

        logger.debug(
            f"Restored pipeline to {len(stashed_entries)} entries from '{self.key}'."
        )
        return stashed_entries
