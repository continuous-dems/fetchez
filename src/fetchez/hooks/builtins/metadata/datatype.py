#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.metadata.datatype
~~~~~~~~~~~~~

Generates a 'sidecar' metadata file for each entry

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class SetDataType(FetchHook):
    """Overrides the data_type attribute of pipeline entries.
    Useful for mapping generic files to specific parser profiles.

    Usage: --hook set_datatype:type=nos_legacy_xyz
    """

    name = "set_datatype"
    desc = "Override the data_type of pipeline entries."
    stage = "file"
    category = "metadata"

    def __init__(self, data_type=None, **kwargs):
        super().__init__(**kwargs)
        self.data_type = data_type

    def run(self, entries):
        if not self.data_type:
            return entries

        for mod, entry in entries:
            if entry.get("status") == 0:
                old_type = entry.get("data_type", "unknown")
                entry["data_type"] = self.data_type
                logger.debug(
                    f"Changed data_type from '{old_type}' to '{self.data_type}' for {entry.get('dst_fn')}"
                )

        return entries
