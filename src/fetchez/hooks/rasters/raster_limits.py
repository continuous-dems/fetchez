#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
globato.hooks.rasters.raster_limits
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Apply limits to a raster z/w/u/etc.

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import numpy as np
import logging

from fetchez.utils import float_or
from fetchez.hooks.rasters import RasterHook

logger = logging.getLogger(__name__)


class RasterLimitsHook(RasterHook):
    """Applies Z-limits and other constraints to a chunked raster stream.
    Replaces values outside the limits with NoData.
    """

    name = "test-raster-limits"
    meta_stage = "stream"
    meta_category = "raster"
    meta_desc = "Applies limits to a raster stream."
    meta_aliases = ["raster_limits"]

    def __init__(self, lower=None, upper=None, **kwargs):
        super().__init__(**kwargs)
        self.lower = float_or(lower)
        self.upper = float_or(upper)

    def process_chunk(self, chunk, entry):
        data = chunk["data"].copy()
        nodata = chunk["nodata"]
        mask = chunk.get("mask")
        valid = mask != 0 if mask is not None else np.ones_like(data, dtype=bool)

        valid_mask = (valid) & (data != nodata) & (~np.isnan(data))

        if not np.any(valid_mask):
            return data

        if self.lower is not None:
            valid_mask &= data >= self.lower
        if self.upper is not None:
            valid_mask &= data <= self.upper

        data[~valid_mask] = nodata

        return {**chunk, "data": data}
