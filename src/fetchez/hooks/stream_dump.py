#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.stream_dump
~~~~~~~~~~~~~

This dumps the contents of a stream

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import pprint
import logging
import threading

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()


class StreamDump(FetchHook):
    """Auto-detects file type and attaches a stream."""

    name = "stream-dump"
    meta_stage = "stream"
    meta_desc = "Dump the contents of a stream."
    meta_category = "streams"
    meta_requires = "Any"
    meta_aliases = ["stream_dump"]
    meta_effects = ["consumes-stream"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reader_kwargs = kwargs

    def run(self, entries):
        for _mod, entry in entries:
            if entry.get("stream") or entry.get("raster_stream"):
                for chunk in entry.get("stream"):
                    contents = chunk
                    with PRINT_LOCK:
                        pprint.pprint(contents)

        return entries
