#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Write Fetchez raster-stream chunks to GeoTIFFs.

Chunks use source-relative ``window`` and ``read_window`` coordinates. The
shared ``RasterContext.profile`` defines the destination grid, while
``context.metadata['selection_window']`` defines its source-grid origin.

In inline mode writing is *lazy*: a file is published and the artifact is
registered only after the upstream stream is fully consumed. In drain mode
this hook immediately consumes the stream and updates the entry's ``dst_fn``.
"""

import itertools
import logging
import os
import tempfile
from pathlib import Path

import rasterio
from rasterio.windows import Window

from fetchez.hooks import FetchHook
from fetchez.utils import str2bool

logger = logging.getLogger(__name__)


class RasterWrite(FetchHook):
    """Write a raster stream to a file, optionally passing chunks downstream.

    By default each input writes beside its ``dst_fn`` as ``<stem><suffix>.tif``.
    ``output_path`` may be a directory, a single explicit filename (only for
    one entry), or a format string containing ``{stem}``, ``{name}``,
    ``{suffix}`` and ``{index}`` for multiple entries.

    ``drain=False`` attaches a lazy tap to ``entry['stream']``; a downstream
    consumer must exhaust that stream to complete the output. ``drain=True``
    consumes it immediately and replaces the entry's file reference.
    """

    name = "test-raster-write"
    meta_stage = "stream"
    meta_category = "raster"
    meta_desc = "Write raster-stream chunks to GeoTIFF files."
    meta_accepts = "raster-stream"
    # Drain removes the stream; inline passes through raster-stream.
    meta_produces = "raster-stream"
    meta_aliases = ["raster-stream-write-raster", "raster_write"]

    def __init__(
        self, output_path=None, suffix="_final", artifact_id=None, drain=False, **kwargs
    ):
        super().__init__(**kwargs)
        self.output_path = output_path
        self.suffix = suffix
        self.artifact_id = artifact_id or self.name
        self.drain = str2bool(drain)

    def _output_name(self, entry, index, total):
        source = os.fspath(entry.get("dst_fn") or "out")
        stem = Path(source).stem
        if self.output_path is None:
            return Path(source).with_name(f"{stem}{self.suffix}.tif")

        template = os.fspath(self.output_path)
        if "{" in template:
            try:
                path = template.format(
                    stem=stem, name=Path(source).name, suffix=self.suffix, index=index
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"Invalid raster output_path template {template!r}"
                ) from exc

            return Path(path).resolve()

        if template.endswith(os.sep) or Path(template).is_dir():
            return Path(Path(template) / f"{stem}{self.suffix}.tif").resolve()

        if total > 1:
            raise ValueError(
                "Explicit output_path filename requires one raster entry; "
                "use a directory or {stem}/{index} template for multiple entries"
            )

        return Path(template).resolve()

    @staticmethod
    def _write_chunk(dst, chunk, selection, band_mapping):
        window = chunk["window"]
        read_window = chunk.get("read_window", window)
        data = chunk["data"]
        if data is None:
            raise ValueError("RasterWrite requires eagerly loaded chunk['data']")

        yoff = int(window.row_off - read_window.row_off)
        xoff = int(window.col_off - read_window.col_off)
        height, width = int(window.height), int(window.width)
        if min(yoff, xoff) < 0:
            raise ValueError("Core window extends outside read_window")

        out_window = Window(
            int(window.col_off - selection.col_off),
            int(window.row_off - selection.row_off),
            width,
            height,
        )
        if (
            out_window.col_off < 0
            or out_window.row_off < 0
            or out_window.col_off + width > dst.width
            or out_window.row_off + height > dst.height
        ):
            raise ValueError(f"Chunk window {window} outside output raster extent")

        if data.ndim == 3:
            core = data[:, yoff : yoff + height, xoff : xoff + width]
            indices = tuple(chunk.get("band_indices", range(1, data.shape[0] + 1)))
            if len(indices) != core.shape[0]:
                raise ValueError("band_indices and data band count disagree")

            mapped = [band_mapping.get(b) for b in indices]
            if any(b is None for b in mapped):
                raise ValueError(f"Unmapped raster bands: {indices!r}")

            if core.shape[1:] != (height, width):
                raise ValueError("Chunk array does not contain the core window")

            dst.write(core, indexes=mapped, window=out_window)
        elif data.ndim == 2:
            core = data[yoff : yoff + height, xoff : xoff + width]
            if core.shape != (height, width):
                raise ValueError("Chunk array does not contain the core window")

            band = chunk.get("band_index", 1)
            target = band_mapping.get(band)
            if target is None:
                raise ValueError(f"Unmapped raster band {band!r}")

            dst.write(core, target, window=out_window)
        else:
            raise ValueError(f"Expected 2D or 3D raster array, got {data.ndim}D")

    @staticmethod
    def _set_band_metadata(dst, chunk, band_mapping, written):
        if "band_indices" in chunk:
            indices = chunk["band_indices"]
            descriptions = chunk.get("band_descriptions", ())
            units = chunk.get("band_units", ())
            _nodata = chunk.get("nodata", ())
        else:
            indices = (chunk.get("band_index", 1),)
            descriptions = (chunk.get("band_description"),)
            units = (chunk.get("band_unit"),)
            _nodata = (chunk.get("nodata"),)

        for i, src_band in enumerate(indices):
            target = band_mapping[src_band]
            if target in written:
                continue

            if i < len(descriptions) and descriptions[i]:
                dst.set_band_description(target, descriptions[i])

            if i < len(units) and units[i]:
                dst.set_band_unit(target, units[i])

            written.add(target)

    def _write_stream(self, stream, dst_fn, entry):
        """Consume and forward *every* chunk, publishing only on exhaustion."""
        iterator = iter(stream)
        first = next(iterator, None)
        if first is None:
            raise ValueError(f"{self.name}: empty raster stream; cannot derive profile")

        context = first.get("context")
        if context is None:
            raise ValueError("Raster stream chunk has no 'context'")

        profile = context.profile.copy()
        selection = context.metadata.get("selection_window")
        if selection is None:
            selection = Window(0, 0, profile["width"], profile["height"])

        if first["data"].ndim == 3:
            band_indices = tuple(
                first.get("band_indices", range(1, first["data"].shape[0] + 1))
            )
            if len(band_indices) != profile["count"]:
                raise ValueError("Output profile count does not match stacked bands")
        else:
            # The default single-band reader profile has count=1. A single
            # selected source band (e.g. band 3) maps to destination band 1.
            if profile["count"] == 1:
                band_indices = (first.get("band_index", 1),)
            else:
                band_indices = tuple(range(1, profile["count"] + 1))

        band_mapping = {band: i for i, band in enumerate(band_indices, start=1)}
        if not all(isinstance(c, int) for c in (profile["width"], profile["height"])):
            raise ValueError("Output profile must have integral dimensions")

        dst_fn.parent.mkdir(parents=True, exist_ok=True)
        if context.source and Path(os.fspath(context.source)).resolve() == dst_fn:
            raise ValueError("Refusing to overwrite the raster being read")

        fd, tmp = tempfile.mkstemp(
            prefix=".raster-write-", suffix=".tif", dir=dst_fn.parent
        )
        os.close(fd)
        published = False
        try:
            with rasterio.open(tmp, "w", **profile) as dst:
                tags = context.metadata.get("tags", {})
                if tags:
                    dst.update_tags(**tags)
                written = set()

                for chunk in itertools.chain((first,), iterator):
                    if chunk.get("context") is not context:
                        raise ValueError(
                            "RasterWrite cannot combine multiple raster contexts"
                        )

                    self._write_chunk(dst, chunk, selection, band_mapping)
                    self._set_band_metadata(dst, chunk, band_mapping, written)
                    yield chunk

            os.replace(tmp, dst_fn)
            published = True
            entry.setdefault("artifacts", {})[self.artifact_id] = dst_fn
            logger.info("Wrote raster stream to %s", dst_fn)
        finally:
            if not published and tmp.exists():
                tmp.unlink()

    def run(self, entries):
        result = list(entries)
        rasters = [
            (mod, entry) for mod, entry in result if entry.get("stream") is not None
        ]
        paths = set()
        for idx, (_mod, entry) in enumerate(rasters):
            if entry.get("stream_type") != "raster-stream":
                raise TypeError(
                    f"{self.name}: expected raster-stream, got "
                    f"{entry.get('stream_type')!r}"
                )

            path = self._output_name(entry, idx, len(rasters))
            if path in paths:
                raise ValueError(f"Raster output collision: {path}")

            paths.add(path)
            writer = self._write_stream(entry["stream"], path, entry)
            if self.drain:
                for _ in writer:
                    pass
                entry.pop("stream", None)
                entry.pop("stream_type", None)
                entry["dst_fn"] = path
            else:
                entry["stream"] = writer

        return result
