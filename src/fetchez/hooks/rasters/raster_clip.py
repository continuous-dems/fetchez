#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.rasters.raster_clip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Clip a raster to a vector

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import numpy as np

from .base import RasterHook

logger = logging.getLogger(__name__)


class RasterClipHook(RasterHook):
    """Clips a raster array using vector geometries."""

    name = "test-raster-clip"
    default_suffix = "_clipped"
    meta_desc = "Clip a raster using vector geometries."
    # xmeta_aliases = ["raster_clip"]

    def __init__(self, invert=False, **kwargs):
        super().__init__(**kwargs)

        self.invert = str(invert).lower() == "true"

        logger.debug(f"Clipping {self.name} with {self.barrier}")

    def process_chunk(self, chunk, entry):
        """Process individual windows/chunks passed by RasterHook."""

        data = chunk["data"]
        nodata = chunk.context["nodata"]
        out_shape = data.shape[-2:] if data.ndim >= 2 else data.shape
        geom_mask = self._create_barrier_mask(out_shape, chunk["transform"])

        if geom_mask is None:
            return chunk

        if data.ndim == 3:
            geom_mask = np.broadcast_to(geom_mask, data.shape)

        if self.invert:
            return np.where(~geom_mask, data, nodata)
        else:
            return np.where(geom_mask, data, nodata)
