#!/usr/bin/env python

"""
fetchez.hooks.set_weight
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assigns processing weights to data entries based on module name or patterns.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os

from fetchez.hooks import FetchHook
from fetchez.utils import parse_arg_to_dict

logger = logging.getLogger(__name__)


class SetWeight(FetchHook):
    """Assigns weights to entries based on rules.

    Usage:
        # Universal default
        --hook set_weight:default=0.5

        # Rule-based override
        --hook set_weight:rules=nos_hydro=10.0/lidar=5.0/csb=0.5

        # Specific match_key override
        --hook set_weight:match_key=year,rules=2015=2.0/2016=3.5
    """

    name = "set-weight"
    meta_desc = "Assigns weights to entries"
    meta_stage = "manifest"  # pre
    meta_category = "metadata"
    meta_aliases = ["set_weight"]

    def __init__(self, default=1.0, rules=None, match_key=None, **kwargs):
        super().__init__(**kwargs)
        self.default = float(default)
        self.match_key = match_key

        self.rules = parse_arg_to_dict(rules, cast_type=float)
        self.rules = {str(k).lower(): float(v) for k, v in self.rules.items()}

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
                elif entry.get("datatype"):
                    keys_to_check.append(str(entry.get("datatype")).lower())

                dst_fn = entry.get("dst_fn")
                if dst_fn:
                    keys_to_check.append(dst_fn.lower())
                    _, ext = os.path.splitext(dst_fn)
                    if ext:
                        keys_to_check.append(ext.lower().lstrip("."))

            assigned_weight = self.default
            match_found = False

            for key in keys_to_check:
                for rule_key, rule_val in self.rules.items():
                    if rule_key in key:
                        assigned_weight = rule_val
                        match_found = True
                        break
                if match_found:
                    break

            entry["weight"] = assigned_weight

            if match_found:
                logger.debug(
                    f"Assigned weight {assigned_weight} to {os.path.basename(entry.get('dst_fn', ''))} (Matched rule)"
                )
            else:
                logger.debug(
                    f"Assigned default weight {assigned_weight} to {os.path.basename(entry.get('dst_fn', ''))}"
                )

        return entries
