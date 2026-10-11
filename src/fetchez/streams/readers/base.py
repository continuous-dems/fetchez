#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.streams.readers.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base fetchez Reader class to create 'streams'

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.spatial import Region

logger = logging.getLogger(__name__)


class BaseReader:
    """The base class for fetchez data Readers"""

    def __init__(self, path, region=None, **kwargs):
        self.path = path
        if region is not None and not isinstance(region, Region):
            try:
                self.region = Region.from_list(region)
            except Exception:
                self.region = region
        else:
            self.region = region

        self.infos = {}
        self.kwargs = kwargs

    def _read_chunks(self):
        """Subclasses MUST implement this to yield their specific data chunks."""

        raise NotImplementedError

    def _extract_bounds(self, chunk):
        """Subclasses implement this to return (xmin, xmax, ymin, ymax, zmin, zmax, count)
        for a given chunk.
        """

        raise NotImplementedError

    def yield_chunks(self):
        yield from self._read_chunks()
