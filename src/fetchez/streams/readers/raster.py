#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.streams.readers.raster
~~~~~~~~~~~~~

Raster data parsing with rasterio

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window
from rasterio.errors import CRSError


from .base import BaseReader

logger = logging.getLogger(__name__)
logging.getLogger("rasterio").setLevel(logging.ERROR)


class RasterReader(BaseReader):
    """Streaming Raster Parser using Rasterio."""

    name = "rasterio"

    meta_category = "raster"
    meta_produces = "raster-stream"

    # meta_dtype = ["rio", "rasterio", "rio-raster", "raster"]
    meta_desc = "Read raster bands as windowed raster data streams."
    # meta_extensions = ["tif", "tiff", "vrt"]

    # Cell strip count.
    STRIP_CHUNK_CELLS = 500_000

    def __init__(
        self,
        path,
        chunk_size=None,
        region=None,
        bands=None,
        band_mode="stack",
        include_mask=True,
        path_prefix="",
        path_suffix="",
        src_srs=None,
        **kwargs,
    ):
        super().__init__(path, region=region, **kwargs)

        if path_prefix or path_suffix:
            self.src_fn = f"{path_prefix}{path}{path_suffix}"
        else:
            self.src_fn = path

        if band_mode not in {"single", "stack"}:
            raise ValueError("band_mode must be 'single' or 'stack'")

        self.bands = tuple(bands) if bands is not None else None
        self.band_mode = band_mode
        self.include_mask = include_mask

        self.chunk_size = chunk_size
        self.src_srs = src_srs
        self.kwargs = kwargs

    def get_srs(self):
        """Get source SRS."""
        if self.src_srs:
            return self.src_srs

        if getattr(self, "srs", None):
            return self.srs

        try:
            with rasterio.Env(CPL_MIN_LOG_LEVEL=rasterio.logging.ERROR):
                with rasterio.open(self.src_fn) as src:
                    return src.crs.to_wkt() if src.crs else "EPSG:4326"
        except Exception:
            return "EPSG:4326"

    def _crop_crs(self, src):
        """Horizontal CRS used to crop the raster to the region.

        src_srs can carry a vertical datum that only transformez understands
        (e.g. 'EPSG:32611+vdatum:mllw'); the crop needs just the horizontal part.
        """

        srs = str(self.src_srs).strip() if getattr(self, "src_srs", None) else None
        if srs:
            if "+" in srs and not srs.startswith("+") and "[" not in srs:
                srs = srs.split("+")[0]
            try:
                return CRS.from_user_input(srs)
            except CRSError:
                logger.warning(
                    f"Unrecognized src_srs '{self.src_srs}' for {self.src_fn}; "
                    "using the file's own CRS to crop."
                )

        return src.crs or CRS.from_epsg(4326)

    def _read_chunks(self):
        yield from self._process_rio_dataset()
        return

    def _process_rio_dataset(self, src=None):
        """Yield chunks using Rasterio Windows. Accepts an optional open dataset."""

        if src is not None:
            yield from self._read_chunks_from_src(src)
        else:
            try:
                with rasterio.Env(CPL_MIN_LOG_LEVEL=rasterio.logging.ERROR):
                    with rasterio.open(self.src_fn) as new_src:
                        yield from self._read_chunks_from_src(new_src)
            except Exception as e:
                logger.exception(f"Rasterio read failed: {e}")
                raise

    def _read_chunks_from_src(self, src):
        """The core windowing and extraction logic, isolated from file-opening."""

        src_crs = self._crop_crs(src)
        if self.region:
            crop_region = self.region.copy()

            region_srs = crop_region.srs or "EPSG:4326"
            src_crs = self._crop_crs(src)

            if CRS.from_user_input(region_srs) != src_crs:
                crop_region.warp(str(src_crs))

            col, row, width, height = crop_region.to_window(
                src.transform,
                width=src.width,
                height=src.height,
            )

            if width == 0 or height == 0:
                return

            master_window = Window(col, row, width, height)
        else:
            master_window = Window(0, 0, src.width, src.height)

        y_start = int(master_window.row_off)
        y_end = int(master_window.row_off + master_window.height)
        x_start = int(master_window.col_off)
        x_end = int(master_window.col_off + master_window.width)

        # If blocks span the full width, the file is stored in strips of block_h
        # rows. Each strip gives block_h * (cropped width) cells; take the number of
        # whole strips needed to reach STRIP_CHUNK_CELLS (-(-a // b) rounds a / b
        # up), and at least one.
        block_h, block_w = src.block_shapes[0]
        if not self.chunk_size and block_w >= src.width:
            strips = -(-self.STRIP_CHUNK_CELLS // (block_h * (x_end - x_start)))
            block_h *= max(strips, 1)
        h_chunk = self.chunk_size or block_h
        w_chunk = self.chunk_size or block_w

        band_indices = self.bands if self.bands is not None else tuple(src.indexes)

        for y in range(y_start, y_end, h_chunk):
            rows = min(h_chunk, y_end - y)

            for x in range(x_start, x_end, w_chunk):
                cols = min(w_chunk, x_end - x)
                window = Window(x, y, cols, rows)

                common = {
                    "window": window,
                    "transform": src.window_transform(window),
                    "crs": src_crs,
                }

                if self.band_mode == "stack":
                    chunk = {
                        **common,
                        "data": src.read(
                            indexes=list(band_indices),
                            window=window,
                        ),
                        "band_indices": band_indices,
                        "nodata": tuple(
                            src.nodatavals[src.indexes.index(i)] for i in band_indices
                        ),
                        "band_units": tuple(
                            src.units[src.indexes.index(i)] for i in band_indices
                        ),
                        "band_descriptions": tuple(
                            src.descriptions[src.indexes.index(i)] for i in band_indices
                        ),
                    }

                    if self.include_mask:
                        chunk["mask"] = src.read_masks(
                            indexes=list(band_indices),
                            window=window,
                        )

                    yield chunk

                else:
                    for band_idx in band_indices:
                        chunk = {
                            **common,
                            "data": src.read(
                                band_idx,
                                window=window,
                            ),
                            "band_index": band_idx,
                            "nodata": src.nodatavals[src.indexes.index(band_idx)],
                        }

                        if self.include_mask:
                            chunk["mask"] = src.read_masks(
                                band_idx,
                                window=window,
                            )

                        yield chunk
