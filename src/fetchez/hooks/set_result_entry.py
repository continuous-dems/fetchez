#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.set_datatype
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Rule-based assignment of arbitrary Fetchez entry fields.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import copy
import fnmatch
import logging
from pathlib import Path

from fetchez.hooks import FetchHook
from fetchez.utils import parse_arg_to_dict

logger = logging.getLogger(__name__)


class SetEntryKey(FetchHook):
    """Set an entry field using a value, filename match, or ordered rules.

    ``key`` names the entry field to modify. ``match_key`` selects the
    source field to inspect (``dst_fn`` by default, or ``module``).
    Patterns use case-insensitive shell-style glob matching.

    ``match_mode='substring'`` is provided for legacy rule semantics.
    """

    name = "set-entry"
    meta_desc = "Assign arbitrary entry metadata using matching rules."
    meta_stage = "manifest"
    meta_category = "metadata"
    meta_aliases = ["set_entry", "set-entry-key", "set_entry_key"]

    def __init__(
        self,
        key=None,
        value=None,
        match=None,
        match_key="dst_fn",
        rules=None,
        default=None,
        overwrite=False,
        match_mode="glob",
        **kwargs,
    ):
        super().__init__(**kwargs)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("set-entry requires a non-empty 'key'")
        if match_mode not in {"glob", "substring"}:
            raise ValueError("match_mode must be 'glob' or 'substring'")
        if match is not None and value is None:
            raise ValueError("match requires a non-None value")
        if rules is not None and not isinstance(rules, (dict, str)):
            raise TypeError("rules must be a mapping or legacy rule string")
        self.key = key
        self.value = copy.deepcopy(value)
        self.match = match
        self.match_key = match_key
        self.rules = (
            copy.deepcopy(rules)
            if isinstance(rules, dict)
            else parse_arg_to_dict(rules, cast_type=str)
            if rules
            else {}
        )
        self.default = copy.deepcopy(default)
        self.overwrite = overwrite
        self.match_mode = match_mode

    def _match_value(self, mod, entry):
        if self.match_key == "module":
            return getattr(mod, "name", None)
        return entry.get(self.match_key)

    def _matches(self, pattern, candidate):
        pattern = str(pattern).casefold()
        candidate = str(candidate).casefold()
        if self.match_mode == "substring":
            return pattern in candidate
        # A filename glob can match either the full path or its basename.
        return fnmatch.fnmatchcase(candidate, pattern) or (
            self.match_key == "dst_fn"
            and fnmatch.fnmatchcase(Path(candidate).name, pattern)
        )

    def run(self, entries):
        for mod, entry in entries:
            if not self.overwrite and entry.get(self.key) is not None:
                continue
            candidate = self._match_value(mod, entry)
            selected = None
            matched = False
            if candidate is not None:
                if self.match is not None and self._matches(self.match, candidate):
                    selected, matched = self.value, True
                if not matched:
                    for pattern, rule_value in self.rules.items():
                        if self._matches(pattern, candidate):
                            selected, matched = rule_value, True
                            break
            if not matched:
                if self.match is None and not self.rules and self.value is not None:
                    selected = self.value
                    matched = True
                elif self.default is not None:
                    selected = self.default
                    matched = True
            if matched:
                entry[self.key] = copy.deepcopy(selected)
                logger.debug("Set entry %s for %s", self.key, entry.get("dst_fn"))
        return entries
