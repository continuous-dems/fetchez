#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.base
~~~~~~~~~~~~~~~~~~~~~~

This file holds the FetchHook super class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""


class FetchHook:
    name = "base-hook"

    # --- Registry Metadata ---
    meta_desc = "Does something."
    meta_category = "uncategorized"

    # --- Hook Stages ---
    meta_stage = "file"
    meta_stages = None

    STAGES = (
        "manifest",
        "file",
        "stream",
        "collection",
        "finalize",
    )

    STAGE_ALIASES = {
        "pre": "manifest",
        "post": "collection",
    }

    @classmethod
    def normalize_stage(cls, stage):
        if not isinstance(stage, str):
            raise TypeError(f"Hook stage must be a string, got {type(stage).__name__}")

        stage = stage.lower()
        stage = cls.STAGE_ALIASES.get(stage, stage)

        if stage not in cls.STAGES:
            raise ValueError(
                f"Unknown hook stage {stage!r}; "
                f"expected one of: {', '.join(cls.STAGES)}"
            )

        return stage

    def __init__(self, stage=None, **kwargs):
        self.opts = kwargs

        default_stage = self.normalize_stage(self.meta_stage)
        requested_stage = self.normalize_stage(
            default_stage if stage is None else stage
        )

        if self.meta_stages is not None:
            allowed = {self.normalize_stage(s) for s in self.meta_stages}

            if not allowed:
                raise ValueError(f"Hook {self.name!r} declares no supported stages")

            if default_stage not in allowed:
                raise ValueError(
                    f"Default stage {default_stage!r} is not permitted "
                    f"by meta_stages for hook {self.name!r}"
                )

            if requested_stage not in allowed:
                raise ValueError(
                    f"Hook {self.name!r} does not support stage "
                    f"{requested_stage!r}; supported stages: "
                    f"{', '.join(sorted(allowed))}"
                )

        self.stage = requested_stage
        self.context = None
        self.instance_id = None

    def __eq__(self, other):
        """Hooks are 'equal' if they are the same type and have identical dicts."""
        if not isinstance(other, type(self)):
            return False
        return self.__dict__ == other.__dict__

    def __getstate__(self):
        state = self.__dict__.copy()
        state["context"] = None
        return state

    # ==========================================
    # STREAM HELPERS
    # ==========================================
    def has_stream(self, entry):
        """Check if an entry contains an active data stream."""

        return entry.get("stream") is not None

    def get_stream(self, entry):

        if self.has_stream(entry):
            return entry.get("stream")

        return None

    def get_stream_type(self, entry):
        """Retrieve the stream type."""

        return entry.get("stream_type", "")

    def is_raster_stream(self, entry):
        """Check if the current stream is a raster-stream."""

        return self.has_stream(entry) and self.get_stream_type(entry) == "raster-stream"

    def is_point_stream(self, entry):
        """Check if the current stream is a point-stream."""

        # Leaving xyz_recarray for backward compatibility during the transition
        return self.has_stream(entry) and self.get_stream_type(entry) in [
            "point-stream",
            "xyz_recarray",
        ]

    def is_list_stream(self, entry):
        """Check if the current stream is a list-stream."""

        return self.has_stream(entry) and self.get_stream_type(entry) == "list-stream"

    # ==========================================
    # PIPELINE
    # ==========================================
    def teardown(self):
        """Cleanup.
        Called once after all processing is complete.
        Override this to close files, finalize grids, or print summaries.
        """

        pass

    def run(self, entries):
        """Execute the hook.

        Args:
            entries: A list of (module, entry) tuples representing the active pipeline.

        Returns:
            Modified entries list.
        """

        return entries
