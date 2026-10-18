#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Composite, file-oriented raster processing using Fetchez's stream components.

Place this hook in ``file`` or ``collection``. It creates raster streams from
file entries, runs ordinary raster-stream hooks in their declared order, and
materializes the results with RasterWrite(drain=True). The nested hooks are
executed *inside* this hook, not scheduled by run_fetchez's stream stage.
"""

import inspect
import logging
import os
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class RasterPipeline(FetchHook):
    """Run an ordered raster-stream pipeline against raster files.

    Parameters
    ----------
    hooks : sequence
        Registered hook names, dictionaries such as ``{'name': 'raster-clamp',
        'args': {'lower': 0}}``, FetchHook subclasses, or hook instances.
        Nested hooks must consume and produce ``raster-stream``.
    reader : dict, optional
        RasterReader keyword arguments (excluding the input path). Supports
        ``chunk_size``, ``buffer``, ``bands``, ``region`` etc.
    writer : dict, optional
        RasterWrite keyword arguments, e.g. ``suffix``, ``output_path``.
        The composite always forces ``drain=True``.
    skip_non_raster : bool
        Ignore entries that are not recognized raster file entries. Entries
        explicitly marked ``data_type='raster'`` are always considered.

    Notes
    -----
    A composite writes one output per input and updates its ``dst_fn``. Nested
    hooks must preserve entry cardinality and identity (normal per-chunk hooks
    do). Dataset-wide mosaics belong in a separate collection operation.
    """

    name = "test-raster-pipeline"
    meta_stage = "file"
    meta_category = "raster"
    meta_desc = "Read raster files, apply stream hooks, and write raster results."
    meta_aliases = ["raster_pipeline"]

    RASTER_EXTENSIONS = frozenset(
        {".tif", ".tiff", ".vrt", ".img", ".jp2", ".nc", ".grd"}
    )

    def __init__(
        self,
        hooks=None,
        reader=None,
        writer=None,
        skip_non_raster=True,
        stage=None,
        **kwargs,
    ):
        if stage is not None and stage not in ("file", "collection"):
            raise ValueError("RasterPipeline stage must be 'file' or 'collection'")
        if stage is not None:
            kwargs["stage"] = stage
        super().__init__(**kwargs)
        if stage is not None:
            self.stage = stage
        self.hook_specs = list(hooks or [])
        self.reader_args = dict(reader or {})
        self.writer_args = dict(writer or {})
        self.skip_non_raster = skip_non_raster
        if "path" in self.reader_args:
            raise ValueError("reader.path is supplied from each entry's dst_fn")
        if "drain" in self.writer_args and not self.writer_args["drain"]:
            raise ValueError("RasterPipeline requires writer.drain=True")
        self.writer_args["drain"] = True

    def _is_raster(self, entry):
        kind = entry.get("data_type")
        if kind == "raster":
            return True
        if kind is not None and kind != "raster":
            return False
        path = entry.get("dst_fn")
        return bool(
            path and Path(os.fspath(path)).suffix.lower() in self.RASTER_EXTENSIONS
        )

    @staticmethod
    def _make_hook(spec):
        # Registration is needed only for string names, not Python classes or
        # already-initialized instances used in runtime recipes.
        from fetchez.registry import HookRegistry

        HookRegistry.load_all()

        if isinstance(spec, FetchHook):
            return spec, False
        if isinstance(spec, str):
            name, args = spec, {}
        elif isinstance(spec, dict):
            name = spec.get("name")
            args = dict(spec.get("args") or {})
            if not name:
                raise ValueError(f"RasterPipeline hook missing 'name': {spec!r}")
        elif inspect.isclass(spec) and issubclass(spec, FetchHook):
            return spec(), True
        else:
            raise TypeError(f"Unsupported nested raster hook: {spec!r}")
        if inspect.isclass(name):
            cls = name
        else:
            cls = HookRegistry.get_class(name)
        if cls is None or not inspect.isclass(cls) or not issubclass(cls, FetchHook):
            raise ValueError(f"Unknown or invalid nested raster hook: {name!r}")
        return cls(**args), True

    def _build_hooks(self):
        nested = []
        try:
            for spec in self.hook_specs:
                hook, owned = self._make_hook(spec)
                if hook is self:
                    raise ValueError("RasterPipeline cannot include itself")
                accepts = getattr(hook, "meta_accepts", None)
                produces = getattr(hook, "meta_produces", None)
                if accepts is not None and "raster-stream" not in (
                    (accepts,) if isinstance(accepts, str) else accepts
                ):
                    raise TypeError(
                        f"Nested hook {hook.name!r} does not accept raster-stream"
                    )
                if produces is not None and "raster-stream" not in (
                    (produces,) if isinstance(produces, str) else produces
                ):
                    raise TypeError(
                        f"Nested hook {hook.name!r} does not produce raster-stream"
                    )
                nested.append((hook, owned))
            return nested
        except BaseException:
            self._teardown(nested)
            raise

    @staticmethod
    def _teardown(nested):
        for hook, owned in reversed(nested):
            if owned and hasattr(hook, "teardown"):
                try:
                    hook.teardown()
                except Exception:
                    logger.exception(
                        "Nested raster hook teardown failed: %s", hook.name
                    )

    def run(self, entries):
        """Synchronously process raster file entries and return their replacements.

        The writer drains all nested lazy streams before this method returns,
        including when run_fetchez invokes this hook in the collection stage.
        """
        from fetchez.streams.readers.raster import RasterReader
        from fetchez.hooks.rasters.raster_writer import RasterWrite

        result = list(entries)
        selected = []
        for mod, entry in result:
            if not self._is_raster(entry):
                if not self.skip_non_raster:
                    raise TypeError(f"Not a raster entry: {entry.get('dst_fn')!r}")
                continue
            path = entry.get("dst_fn")
            if not path:
                raise ValueError("Raster entry is missing dst_fn")
            if entry.get("stream") is not None:
                raise ValueError(
                    "RasterPipeline expects materialized files, not active streams"
                )
            selected.append((mod, entry))

        if not selected:
            return result

        nested = self._build_hooks()
        try:
            expected = [id(entry) for _, entry in selected]
            for _mod, entry in selected:
                reader = RasterReader(os.fspath(entry["dst_fn"]), **self.reader_args)
                entry["stream"] = reader.yield_chunks()
                entry["stream_type"] = "raster-stream"

            for hook, _owned in nested:
                selected = hook.run(selected)
                if selected is None or [id(e) for _, e in selected] != expected:
                    raise ValueError(
                        f"Nested raster hook {hook.name!r} changed entry identity/order; "
                        "RasterPipeline currently supports one output per input"
                    )

            RasterWrite(**self.writer_args).run(selected)
            for _, entry in selected:
                if entry.get("stream") is not None:
                    raise RuntimeError("RasterPipeline writer did not drain the stream")
            return result
        finally:
            # A failed nested processing stage must not leave stale, exhausted
            # streams attached to entries. Completed outputs retain their paths.
            for _, entry in selected:
                entry.pop("stream", None)
                entry.pop("stream_type", None)
            self._teardown(nested)
