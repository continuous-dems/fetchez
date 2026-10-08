#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.stream_init
~~~~~~~~~~~~~~~~~~~~~~~~

Initialize generic data streams from Fetchez entries.

Reader resolution is delegated to ReaderRegistry using the entry's
data_type and optional profile.

The resulting stream_type describes the reader's output representation,
not the input data type or selected reader.

Legacy behaviors are isolated for incremental migration.
"""

import logging
import math

from fetchez.hooks import FetchHook
from fetchez.registry import ReaderRegistry
from fetchez.spatial import Region

logger = logging.getLogger(__name__)


class DataStream(FetchHook):
    """Initialize streams from entries using registered readers/profiles.

    Reader selection priority:
      1. Hook-level explicit profile
      2. Entry profile
      3. Hook-level data_type override
      4. Entry data_type and its default profile
      5. Legacy reader dtype/extension fallback

    Parameters
    ----------
    profile : str, optional
        Explicit reader profile to select.
    data_type : str, optional
        Override the entry data type for reader resolution.
    stream_type : str, optional
        Deprecated legacy reader-selection argument.
        Does not set the resulting entry stream_type.
    legacy_entry_kwargs : bool
        Forward arbitrary entry metadata to readers, as older versions
        of stream-init did. Disabled by default.
    legacy_region_mutation : bool
        Preserve historical mutation of module.region after stream
        initialization. Disabled by default.
    **kwargs
        Explicit reader arguments.
    """

    name = "stream-init"
    meta_stage = "stream"
    meta_desc = "Initialize a data stream using registered readers."
    meta_category = "streams"
    meta_requires = "file"
    meta_aliases = ["stream_init", "stream_data"]

    # Historical fields that should never be forwarded automatically.
    _LEGACY_RESERVED_KEYS = frozenset(
        {
            "url",
            "dst_fn",
            "data_type",
            "profile",
            "status",
            "stream",
            "stream_type",
            "history",
            "weight",
            "uncertainty",
        }
    )

    def __init__(
        self,
        profile=None,
        data_type=None,
        stream_type=None,
        legacy_entry_kwargs=False,
        legacy_region_mutation=False,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.profile = profile
        self.data_type = data_type

        # Compatibility only
        self.stream_type = stream_type

        self.legacy_entry_kwargs = legacy_entry_kwargs
        self.legacy_region_mutation = legacy_region_mutation

        self.reader_kwargs = dict(kwargs)

        if stream_type is not None:
            logger.warning(
                "[stream-init] 'stream_type' as a reader selector is "
                "deprecated; use 'profile' or 'data_type' instead."
            )

    # ------------------------------------------------------------------
    # Reader selection
    # ------------------------------------------------------------------

    def _resolution_entry(self, entry):
        """Return a temporary entry with reader-selection overrides.

        The original entry is not modified.
        """
        resolved = entry.copy()

        if self.data_type is not None:
            resolved["data_type"] = self.data_type

        if self.profile is not None:
            resolved["profile"] = self.profile

        elif self.stream_type is not None:
            # LEGACY: old stream_type selected a profile/dtype.
            # An explicit entry profile takes precedence.
            if not resolved.get("profile"):
                resolved["profile"] = self.stream_type

        return resolved

    # ------------------------------------------------------------------
    # Reader arguments
    # ------------------------------------------------------------------

    def _reader_kwargs(self, mod, entry):
        """Build reader arguments from explicit configuration and context.

        The legacy arbitrary-entry forwarding behavior is optional.
        """
        kwargs = dict(self.reader_kwargs)

        if self.legacy_entry_kwargs:
            for key, value in entry.items():
                if key not in self._LEGACY_RESERVED_KEYS:
                    kwargs[key] = value

        # Preserve historical module-level context propagation.
        kwargs["weight"] = getattr(mod, "weight", 1.0)
        kwargs["uncertainty"] = getattr(mod, "uncertainty", 0.0)

        entry_weight = entry.get("weight", 1.0)
        entry_uncertainty = entry.get("uncertainty", 0.0)

        kwargs["weight"] *= entry_weight

        kwargs["uncertainty"] = math.hypot(
            kwargs["uncertainty"],
            entry_uncertainty,
        )

        # Region is supplied separately to ReaderRegistry.
        kwargs.pop("region", None)

        return kwargs

    # ------------------------------------------------------------------
    # Spatial context
    # ------------------------------------------------------------------

    @staticmethod
    def _module_region(mod):
        """Return the module region without modifying the module."""
        region = getattr(mod, "region", None)

        if region is None:
            return None

        if isinstance(region, Region):
            return region

        return Region.from_list(region)

    def _resolve_src_srs(self, entry, reader, reader_kwargs):
        """Resolve source SRS, preserving historical fallback behavior."""
        existing_srs = entry.get("src_srs")

        if existing_srs:
            return existing_srs

        # Compatibility default.
        base_srs = "EPSG:4326"

        if hasattr(reader, "get_srs"):
            base_srs = reader.get_srs() or base_srs

        vert_srs = reader_kwargs.get("vert_srs")

        if vert_srs and "+" not in str(base_srs):
            base_srs = f"{base_srs}+{vert_srs}"

        return base_srs

    # ------------------------------------------------------------------
    # Stream metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _reader_stream_type(reader):
        """Return the stream representation produced by the reader.

        New readers may declare meta_produces. Older readers continue
        using meta_category until they are migrated.
        """
        produces = getattr(reader, "meta_produces", None)

        if isinstance(produces, str) and produces:
            return produces

        return getattr(
            reader,
            "meta_category",
            "generic-stream",
        )

    # ------------------------------------------------------------------
    # Entry initialization
    # ------------------------------------------------------------------

    def _init_entry_stream(self, mod, entry):
        """Resolve and attach a reader stream to one entry."""
        if entry.get("stream") is not None:
            logger.debug(
                "[stream-init] Entry already has a %s stream.",
                entry.get("stream_type", "unknown"),
            )
            return

        src = entry.get("dst_fn")

        if not src:
            logger.debug(
                "[stream-init] Entry has no destination file: %s",
                entry.get("url"),
            )
            return

        resolution_entry = self._resolution_entry(entry)
        reader_kwargs = self._reader_kwargs(mod, entry)
        region = self._module_region(mod)

        reader = ReaderRegistry.get_reader_from_entry(
            resolution_entry,
            region=region,
            **reader_kwargs,
        )

        # Compatibility for the legacy stream_type selector:
        # it historically accepted both profiles and reader dtypes.
        if reader is None and self.stream_type is not None:
            if self.profile is None and not entry.get("profile"):
                reader = ReaderRegistry.get_reader(
                    src,
                    self.stream_type,
                    region=region,
                    **reader_kwargs,
                )

        if reader is None:
            logger.warning(
                "[stream-init] No reader found for %s (data_type=%s, profile=%s).",
                src,
                resolution_entry.get("data_type"),
                resolution_entry.get("profile"),
            )
            return

        raw_stream = reader.yield_chunks()

        if raw_stream is None:
            logger.debug(
                "[stream-init] Reader %s produced no stream.",
                reader.name,
            )
            return

        # LEGACY: preserve module.region mutation if explicitly requested.
        if self.legacy_region_mutation and region is not None:
            mod.region = region

        # Attach only after successful initialization.
        entry["src_srs"] = self._resolve_src_srs(
            entry,
            reader,
            reader_kwargs,
        )

        entry["stream"] = raw_stream
        entry["stream_type"] = self._reader_stream_type(reader)

        logger.debug(
            "[stream-init] Initialized %s using reader %s (stream_type=%s).",
            src,
            reader.name,
            entry["stream_type"],
        )

    # ------------------------------------------------------------------
    # Hook execution
    # ------------------------------------------------------------------

    def run(self, entries):
        """Initialize streams and return the original entry collection."""
        ReaderRegistry.load_all()

        for mod, entry in entries:
            self._init_entry_stream(mod, entry)

        return entries
