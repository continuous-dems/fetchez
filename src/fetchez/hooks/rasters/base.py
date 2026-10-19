#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.rasters.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This hook handles *existing* raster streams. It does not initialize a reader,
open raster files, manage output paths, or write processed arrays to disk.
A stream-init hook (or equivalent) must run before it.

Chunks follow ``fetchez.streams.readers.raster.RasterReader``:
``data`` is the current pipeline pixel array (including any read halo),
``window`` is the non-overlapping core output window, and ``read_window``
identifies the area represented by ``data``. ``context`` is shared metadata.
"""

from fetchez.hooks import FetchHook


class RasterHook(FetchHook):
    """Base for lazy, per-chunk raster-stream transformations.

    Override :meth:`process_chunk` in subclasses. Return a raster chunk dict
    to pass to the next hook, or ``None`` to drop a chunk intentionally.

    Every invocation gets the *upstream* chunk, including any changes made
    by preceding hooks; this base never rereads the original source.

    Subclasses should preserve ``context``, ``window``, ``read_window``, and
    ``transform`` unless they deliberately implement a grid-changing step.
    Dataset-wide context is shared across chunks: do not store per-chunk
    scratch state in it. Prefer copy-on-write when changing ``data``.
    """

    meta_stage = "stream"
    meta_category = "raster-stream"
    meta_accepts = "raster-stream"
    meta_produces = "raster-stream"
    meta_desc = "Process raster-stream chunks."

    def process_chunk(self, chunk, entry):
        """Process one chunk. Return a dict, or None to discard it."""
        raise NotImplementedError("Raster hooks must implement process_chunk()")

    def _process_stream(self, stream, entry):
        """Wrap upstream stream lazily, preserving order and upstream edits."""
        for chunk in stream:
            result = self.process_chunk(chunk, entry)
            if result is None:
                continue
            if not isinstance(result, dict):
                raise TypeError(
                    f"{self.name}: process_chunk() must return a chunk dict or None, "
                    f"not {type(result).__name__}"
                )
            yield result

    def run(self, entries):
        """Attach lazy chunk transformers to entries carrying raster streams.

        Other entries are left untouched. A declared stream type different
        from raster-stream is rejected rather than being silently processed.
        """
        processed = []
        for mod, entry in entries:
            if not self.has_stream(entry):
                processed.append((mod, entry))
                continue

            if not self.is_raster_stream(entry):
                raise TypeError(
                    f"{self.name}: expected raster-stream for "
                    f"{entry.get('dst_fn', '<unnamed>')!r}, got {self.get_stream_type(entry)!r}"
                )

            # Capture each entry and stream in this iteration (not a late-bound
            # closure). No generator is consumed until a downstream consumer asks.
            entry["stream"] = self._process_stream(self.get_stream(entry), entry)
            processed.append((mod, entry))
        return processed
