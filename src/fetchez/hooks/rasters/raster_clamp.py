#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.rasters.raster_clamp
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

import numpy as np

from fetchez.utils import float_or
from fetchez.hooks.rasters import RasterHook


class RasterClamp(RasterHook):
    name = "raster-clamp"
    meta_desc = "Clamp raster values to specified bounds."

    def __init__(self, lower=None, upper=None, **kwargs):
        super().__init__(**kwargs)
        self.lower = float_or(lower)
        self.upper = float_or(upper)

    def process_chunk(self, chunk, entry):
        data = chunk["data"].copy()

        mask = chunk.get("mask")
        valid = mask != 0 if mask is not None else np.ones_like(data, dtype=bool)

        if self.lower is not None:
            data[valid] = np.maximum(data[valid], self.lower)

        if self.upper is not None:
            data[valid] = np.minimum(data[valid], self.upper)

        return {**chunk, "data": data}
