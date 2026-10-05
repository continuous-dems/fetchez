#!/usr/bin/env python

"""
fetchez.hooks.base
~~~~~~~~~~~~~~~~~~~~~~

This file holds the FetchHook super class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""


class FetchHook:
    """Base class for all Fetchez Hooks."""

    name = "base-hook"

    # --- Registry Metadata ---
    meta_desc = "Does something."
    meta_category = "uncategorized"

    # 'manifest':   Runs before downloads, manipulating the URL/metadata list.
    # 'file':       Runs per-file immediately after download/generation.
    # 'stream":     Runs on entry['stream'] right after the file stage.
    # 'collection': Runs once after all per-file operations are finished.
    meta_stage = "file"

    def __init__(self, stage=None, **kwargs):
        self.opts = kwargs

        raw_stage = stage or getattr(self.__class__, "meta_stage", "file")
        stage_aliases = {"pre": "manifest", "post": "collection"}
        mapped_stage = stage_aliases.get(raw_stage.lower(), raw_stage.lower())

        if mapped_stage in ["manifest", "file", "stream", "collection"]:
            self.stage = mapped_stage
        else:
            self.stage = "file"  # Fallback

    def __eq__(self, other):
        """Hooks are 'equal' if they are the same type and have identical dicts."""
        if not isinstance(other, type(self)):
            return False
        return self.__dict__ == other.__dict__

    # ==========================================
    # STREAM HELPERS
    # ==========================================
    def has_stream(self, entry):
        """Check if an entry contains an active data stream."""

        return entry.get("stream") is not None

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

    def run(self, entries):
        """Execute the hook.

        Args:
            entries: A list of (module, entry) tuples representing the active pipeline.

        Returns:
            Modified entries list.
        """

        return entries
