#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.stream_init
~~~~~~~~~~~~~

This turns files into streams.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import math
import logging

from pyproj import CRS
from pyproj.crs import CompoundCRS
from pyproj.exceptions import CRSError

from fetchez.spatial import Region
from fetchez.hooks import FetchHook
from fetchez.registry import ReaderRegistry, ProfileRegistry

logger = logging.getLogger(__name__)


class DataStream(FetchHook):
    """Auto-detects file type and attaches a stream.

    Usage:
      --hook stream-init:stream_type=csv
    """

    name = "stream-init"
    meta_stage = "stream"
    meta_desc = "Setup a data stream from input data."
    meta_category = "streams"
    meta_requires = "file"
    meta_aliases = ["stream_init", "stream_data"]

    def __init__(self, stream_type=None, **kwargs):
        super().__init__(**kwargs)
        self.stream_type = stream_type  # .lower()
        self.reader_kwargs = kwargs

    def run(self, entries):
        ReaderRegistry.load_all()
        ProfileRegistry.load_all()

        for mod, entry in entries:
            if entry.get("stream"):
                logger.debug(
                    f"Entry {entry} already has an attached {entry.get('stream_type')} stream..."
                )
                continue

            src = entry.get("dst_fn")
            if not src:
                logger.debug(f"There is nothing to stream here, {entry}.")
                continue

            kwargs_copy = self.reader_kwargs.copy()
            kwargs_copy["region"] = getattr(mod, "region", None)
            kwargs_copy["weight"] = getattr(mod, "weight", 1.0)
            kwargs_copy["uncertainty"] = getattr(mod, "uncertainty", 0.0)

            reserved_keys = {
                "url",
                "dst_fn",
                "data_type",
                "status",
                "stream",
                "src_srs",
                "stream_type",
                "history",
                "weight",
                "uncertainty",
            }
            for k, v in entry.items():
                if k not in reserved_keys:
                    kwargs_copy[k] = v

            dtype = entry.get("data_type")
            entry_weight = entry.get("weight", 1.0)
            entry_uncertainty = entry.get("uncertainty", 0.0)
            hook_dtype = kwargs_copy.pop("data_type", None)
            dtype = self.stream_type or hook_dtype or dtype
            # if dtype in ProfileRegistry.get_registry():
            # profile_args = ProfileRegistry.get_yaml(dtype)
            # print(profile_args)
            kwargs_copy["weight"] = kwargs_copy.get("weight", 1.0) * entry_weight
            kwargs_copy["uncertainty"] = math.sqrt(
                kwargs_copy.get("uncertainty", 0.0) ** 2 + entry_uncertainty**2
            )
            reader = ReaderRegistry.get_reader(src, dtype, **kwargs_copy)

            # if dtype:
            #    reader = ReaderRegistry.get_reader_for_dtype(dtype)(src, **kwargs_copy)
            # else:
            # reader = ReaderRegistry.get_reader_for_ext(src.split(".")[-1])(
            #     src, **kwargs_copy
            # )
            if not reader:
                logger.warning(f"No reader could be determined for {dtype}: {entry}")
                continue

            logger.debug(f"Stream initiated with the '{reader.name}' reader")

            # raw_stream = reader.yield_chunks()
            # mod.region = Region.from_list(mod.region)
            raw_stream = reader.yield_chunks()

            # Ensure it's a Region object, but don't overwrite if it already is
            # so we don't accidentally strip the SRS!
            if type(mod.region).__name__ != "Region":
                mod.region = Region.from_list(mod.region)

            if raw_stream:
                existing_srs = entry.get("src_srs")

                if existing_srs:
                    base_srs = existing_srs
                    logger.debug(f"[{self.name}] Using pre-defined SRS: {base_srs}")
                else:
                    base_srs = "EPSG:4326"
                    if hasattr(reader, "get_srs"):
                        base_srs = reader.get_srs() or base_srs

                    vert_srs = kwargs_copy.get("vert_srs")
                    if vert_srs:
                        try:
                            horizontal = CRS.from_user_input(base_srs)
                            vertical = CRS.from_user_input(vert_srs)
                        except CRSError:
                            # Retain custom vertical references such as global:mss.
                            if "+" not in base_srs:
                                base_srs = f"{base_srs}+{vert_srs}"
                        else:
                            if len(horizontal.axis_info) == 2:
                                base_srs = CompoundCRS(
                                    f"{horizontal.name} + {vertical.name}",
                                    [horizontal, vertical],
                                ).to_wkt()

                    logger.debug(f"[{self.name}] Using SRS: {base_srs}")

                entry["src_srs"] = base_srs
                entry["stream"] = raw_stream
                # --- Pass any schemas ---
                # entry["stream"] = ensure_schema(
                #     raw_stream, module_weight=w, module_unc=u
                # )
                # entry["stream_type"] = "xyz_recarray"
                entry["stream_type"] = getattr(
                    reader, "meta_category", "generic-stream"
                )

        return entries
