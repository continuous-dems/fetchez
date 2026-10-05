#!/usr/bin/env python

"""
fetchez.streams.readers.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base fetchez Reader class to create 'streams'

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import logging
import math

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

    def generate_inf(self, out_path=None):
        out_path = out_path or f"{self.path}.inf"

        minmax = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
        total_pts = 0

        # Consume the stream directly (do not yield!)
        for chunk in self.yield_chunks():
            if chunk is None or len(chunk) == 0:
                continue

            try:
                xmin, xmax, ymin, ymax, zmin, zmax, count = self._extract_bounds(chunk)
                # minmax = [xmin, xmax, ymin, ymax, zmin, zmax]
                minmax[0] = min(minmax[0], xmin)
                minmax[1] = max(minmax[1], xmax)
                minmax[2] = min(minmax[2], ymin)
                minmax[3] = max(minmax[3], ymax)
                minmax[4] = min(minmax[4], zmin)
                minmax[5] = max(minmax[5], zmax)
                total_pts += count
            except Exception:
                pass  # Silently fail bounds extraction if chunk is weird

        meta = {}

        # Write the .inf file once the stream is completely exhausted
        if total_pts > 0 and minmax[0] != math.inf:
            w, e, s, n = minmax[0], minmax[1], minmax[2], minmax[3]
            wkt = f"POLYGON (({w} {n}, {e} {n}, {e} {s}, {w} {s}, {w} {n}))"

            meta = {
                "numpts": int(total_pts),
                "minmax": [float(x) for x in minmax],
                "wkt": wkt,
            }

            try:
                with open(out_path, "w") as f:
                    json.dump(meta, f, indent=4)
            except Exception:
                logger.debug(f"Could not write inf file {out_path}")

        return meta

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
