#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.streams.readers.raster
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generic, windowed raster reading for Fetchez.

A raster-stream yields eager NumPy arrays. ``window`` is the non-overlapping
output window; ``read_window`` is the potentially buffered input window.
``transform`` describes the pixels in ``data`` (i.e. ``read_window``).

The same RasterContext instance is attached to every chunk from a dataset.
It contains metadata, not a live Rasterio handle or a second pixel store.

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from numbers import Integral

import rasterio
from rasterio.crs import CRS
from rasterio.errors import CRSError
from rasterio.windows import Window

from .base import BaseReader

logger = logging.getLogger(__name__)
logging.getLogger("rasterio").setLevel(logging.ERROR)


class RasterContext:
    """Dataset-level metadata shared by all chunks in one raster stream.

    ``source_profile`` describes the original opened dataset. ``profile``
    describes the selected output grid/bands, and may be replaced by later
    pipeline stages. Never modify the source profile or stash pixel arrays
    here. ``metadata`` is available for extension-specific dataset metadata.
    """

    def __init__(self, source_profile, profile, source=None, metadata=None):
        self.source_profile = source_profile.copy()
        self.profile = profile.copy()
        self.source = source
        self.metadata = dict(metadata or {})


class RasterReader(BaseReader):
    """Read raster windows into generic chunk dictionaries.

    Args:
        chunk_size: ``None`` for native blocks (with strip optimization),
            positive integer for square windows, ``(height, width)`` for
            rectangular windows, or ``'full'`` / ``-1`` for one selected-area
            window. Full windows may allocate very large arrays.
        buffer: Nonnegative number of halo pixels on each side of a window.
            Halos may extend outside the requested region but never outside
            the source dataset. The downstream writer must crop back to
            ``window`` before writing.
    """

    name = "rasterio"
    meta_category = "raster"
    meta_produces = "raster-stream"
    meta_desc = "Read raster bands as windowed raster data streams."
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
        buffer=0,
        **kwargs,
    ):
        super().__init__(path, region=region, **kwargs)
        self.src_fn = f"{path_prefix}{path}{path_suffix}"
        if band_mode not in {"single", "stack"}:
            raise ValueError("band_mode must be 'single' or 'stack'")

        if not isinstance(buffer, Integral) or isinstance(buffer, bool) or buffer < 0:
            raise ValueError("buffer must be a nonnegative integer")

        self.buffer = int(buffer)
        self.chunk_size = self._validate_chunk_size(chunk_size)
        self.bands = tuple(bands) if bands is not None else None
        self.band_mode = band_mode
        self.include_mask = include_mask
        self.src_srs = src_srs
        self.kwargs = kwargs

    @staticmethod
    def _validate_chunk_size(value):
        if value == "full" or value == -1:
            return "full"

        if value is None:
            return None

        if isinstance(value, Integral) and not isinstance(value, bool) and value > 0:
            return int(value)

        if (
            isinstance(value, (tuple, list))
            and len(value) == 2
            and all(
                isinstance(item, Integral) and not isinstance(item, bool) and item > 0
                for item in value
            )
        ):
            return tuple(int(item) for item in value)
        raise ValueError(
            "chunk_size must be None, positive integer, (height, width), or 'full'"
        )

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
        """Horizontal CRS for cropping, stripping transformez vertical suffixes."""
        srs = str(self.src_srs).strip() if self.src_srs else None
        if srs:
            if "+" in srs and not srs.startswith("+") and "[" not in srs:
                srs = srs.split("+")[0]

            try:
                return CRS.from_user_input(srs)
            except CRSError:
                logger.warning(
                    "Unrecognized src_srs '%s' for %s; using file CRS to crop.",
                    self.src_srs,
                    self.src_fn,
                )
        return src.crs or CRS.from_epsg(4326)

    def _read_chunks(self):
        yield from self._process_rio_dataset()

    def _process_rio_dataset(self, src=None):
        """Yield windows; optionally use a caller-owned open Rasterio dataset."""
        if src is not None:
            yield from self._read_chunks_from_src(src)

        else:
            try:
                with rasterio.Env(CPL_MIN_LOG_LEVEL=rasterio.logging.ERROR):
                    with rasterio.open(self.src_fn) as new_src:
                        yield from self._read_chunks_from_src(new_src)
            except Exception:
                logger.exception("Rasterio read failed: %s", self.src_fn)
                raise

    def _selected_window(self, src, src_crs):
        if not self.region:
            return Window(0, 0, src.width, src.height)
        crop_region = self.region.copy()
        region_srs = crop_region.srs or "EPSG:4326"
        if CRS.from_user_input(region_srs) != src_crs:
            crop_region.warp(str(src_crs))

        col, row, width, height = crop_region.to_window(
            src.transform,
            width=src.width,
            height=src.height,
        )
        # Normalize and clip once so 'full' and halos operate on legal windows.
        x0 = max(0, min(src.width, int(col)))
        y0 = max(0, min(src.height, int(row)))
        x1 = max(x0, min(src.width, int(col + width)))
        y1 = max(y0, min(src.height, int(row + height)))
        return Window(x0, y0, x1 - x0, y1 - y0)

    def _chunk_shape(self, src, selection):
        if self.chunk_size == "full":
            return int(selection.height), int(selection.width)

        if isinstance(self.chunk_size, tuple):
            return self.chunk_size

        if self.chunk_size is not None:
            return self.chunk_size, self.chunk_size

        block_h, block_w = src.block_shapes[0]
        if block_w >= src.width:
            cells_per_strip = block_h * int(selection.width)
            strips = -(-self.STRIP_CHUNK_CELLS // cells_per_strip)
            block_h *= max(1, strips)

        return block_h, block_w

    def _read_window(self, src, window):
        b = self.buffer
        x0 = max(0, int(window.col_off) - b)
        y0 = max(0, int(window.row_off) - b)
        x1 = min(src.width, int(window.col_off + window.width) + b)
        y1 = min(src.height, int(window.row_off + window.height) + b)
        return Window(x0, y0, x1 - x0, y1 - y0)

    def _read_chunks_from_src(self, src):
        """Produce eager chunks with shared profile context and optional halos."""
        src_crs = self._crop_crs(src)
        selection = self._selected_window(src, src_crs)
        if not selection.width or not selection.height:
            return

        bands = self.bands if self.bands is not None else tuple(src.indexes)
        if not bands or any(
            not isinstance(i, Integral) or i not in src.indexes for i in bands
        ):
            raise ValueError(
                f"Invalid raster bands {bands!r}; available: {src.indexes!r}"
            )

        selected_profile = src.profile.copy()
        selected_profile.update(
            width=int(selection.width),
            height=int(selection.height),
            transform=src.window_transform(selection),
            count=len(bands) if self.band_mode == "stack" else 1,
        )
        context = RasterContext(
            source_profile=src.profile,
            profile=selected_profile,
            source=src.name,
            metadata={"tags": src.tags().copy(), "selection_window": selection},
        )

        h_chunk, w_chunk = self._chunk_shape(src, selection)
        y_start, x_start = int(selection.row_off), int(selection.col_off)
        y_end = y_start + int(selection.height)
        x_end = x_start + int(selection.width)

        for y in range(y_start, y_end, h_chunk):
            for x in range(x_start, x_end, w_chunk):
                window = Window(x, y, min(w_chunk, x_end - x), min(h_chunk, y_end - y))
                read_window = self._read_window(src, window)
                common = {
                    "context": context,
                    "window": window,
                    "read_window": read_window,
                    "transform": src.window_transform(read_window),
                    "crs": src_crs,
                }

                if self.band_mode == "stack":
                    chunk = {
                        **common,
                        "data": src.read(indexes=list(bands), window=read_window),
                        "band_indices": bands,
                        "nodata": tuple(src.nodatavals[i - 1] for i in bands),
                        "band_units": tuple(src.units[i - 1] for i in bands),
                        "band_descriptions": tuple(
                            src.descriptions[i - 1] for i in bands
                        ),
                    }

                    if self.include_mask:
                        chunk["mask"] = src.read_masks(
                            indexes=list(bands), window=read_window
                        )
                    yield chunk
                else:
                    for band in bands:
                        chunk = {
                            **common,
                            "data": src.read(band, window=read_window),
                            "band_index": band,
                            "nodata": src.nodatavals[band - 1],
                        }
                        if self.include_mask:
                            chunk["mask"] = src.read_masks(band, window=read_window)

                        yield chunk
