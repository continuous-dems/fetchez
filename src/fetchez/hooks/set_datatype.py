#!/usr/bin/env python

"""
fetchez.hooks.set_datatype
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assigns the data_tpe to data entries based on module name or patterns.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os

from fetchez.hooks import FetchHook
from fetchez.utils import parse_arg_to_dict

logger = logging.getLogger(__name__)


class SetDatatype(FetchHook):
    """Overrides the data_type attribute of pipeline entries based on rules.

    Usage:
        # Override all to 'bag'
        --hook set_datatype:default=bag

        # Override based on extension
        --hook set_datatype:rules=laz=lidar/tif=raster

        # Override based on a specific attribute
        --hook set_datatype:match_key=year,rules=2015=bag/2016=xyz
    """

    name = "set-datatype"
    meta_desc = "Override the data_type of pipeline entries based on rules."
    meta_stage = "manifest"
    meta_category = "metadata"
    meta_aliases = ["set_datatype"]

    def __init__(
        self, data_type=None, default=None, rules=None, match_key=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.default = default if default is not None else data_type
        self.match_key = match_key

        self.rules = parse_arg_to_dict(rules, cast_type=str)
        self.rules = {str(k).lower(): str(v) for k, v in self.rules.items()}

    def run(self, entries):
        for mod, entry in entries:
            keys_to_check = []

            # Specific requested key
            if self.match_key:
                val = entry.get(self.match_key)
                if val is not None:
                    keys_to_check.append(str(val).lower())

            # Broad search
            else:
                if getattr(mod, "name", None):
                    keys_to_check.append(str(mod.name).lower())
                if entry.get("data_type"):
                    keys_to_check.append(str(entry.get("data_type")).lower())
                dst_fn = entry.get("dst_fn")
                if dst_fn:
                    keys_to_check.append(dst_fn.lower())
                    _, ext = os.path.splitext(dst_fn)
                    if ext:
                        keys_to_check.append(ext.lower().lstrip("."))

            assigned_dt = self.default
            match_found = False

            for key in keys_to_check:
                for rule_key, rule_val in self.rules.items():
                    if rule_key in key:
                        assigned_dt = rule_val
                        match_found = True
                        break
                if match_found:
                    break

            if assigned_dt is not None:
                old_dt = entry.get("data_type", "unknown")
                if old_dt != assigned_dt:
                    entry["data_type"] = assigned_dt
                    logger.debug(
                        f"Changed data_type from '{old_dt}' to '{assigned_dt}' "
                        f"for {os.path.basename(entry.get('dst_fn', ''))}"
                    )

        return entries
