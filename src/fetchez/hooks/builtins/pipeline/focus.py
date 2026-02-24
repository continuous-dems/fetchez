#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.pipeline.focus
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pipeline control hooks for artifact focus.
"""

import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class FocusSink(FetchHook):
    """Shrinks the pipeline entries down to the output of a specific Sink/Hook.
    Subsequent Post-Hooks will only act on these generated artifacts.

    The target hook must adhere to the 'Artifact Protocol' by registering
    its outputs in `entry['artifacts'][hook_name] = output_path`.

    Usage:
      --hook focus_sink:target=simple_stack
    """

    name = "focus_sink"
    stage = "post"
    category = "pipeline"

    def __init__(self, target=None, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    def run(self, entries):
        if not self.target:
            logger.warning("FocusSink: No target specified. Ignoring.")
            return entries

        new_entries = []
        seen_paths = set()

        for mod, entry in entries:
            artifacts = entry.get("artifacts", {})

            if self.target in artifacts:
                # Artifacts can be a single path or a list of paths
                artifact_paths = artifacts[self.target]
                if isinstance(artifact_paths, str):
                    artifact_paths = [artifact_paths]

                for path in artifact_paths:
                    if path not in seen_paths:
                        seen_paths.add(path)

                        focused_entry = {
                            "url": f"file://{path}",
                            # "src_fn": entry.get("dst_fn"),
                            "dst_fn": path,
                            "status": 0,
                            "data_type": f"{self.target}_artifact",
                            "artifacts": artifacts,
                        }
                        new_entries.append((mod, focused_entry))

        logger.info(
            f"FocusSink: Shrunk pipeline to {len(new_entries)} '{self.target}' artifacts."
        )
        return new_entries
