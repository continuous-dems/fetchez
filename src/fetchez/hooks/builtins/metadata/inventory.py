#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.metadata.inventory
~~~~~~~~~~~~~

Generate an inventory of (pre) of the fetchez operation.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import csv
import logging
from io import StringIO

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Inventory(FetchHook):
    name = "inventory"
    desc = "Output metadata inventory (JSON/CSV). Usage: --hook inventory:format=csv"
    stage = "pre"
    category = "metadata"

    def __init__(self, format="json", **kwargs):
        super().__init__(**kwargs)
        self.format = format.lower()

    def run(self, entries):
        # Convert (mod, entry) tuples to dicts for reporting
        inventory_list = []
        for mod, entry in entries:
            item = {
                "module": mod.name,
                "filename": entry.get("dst_fn"),
                "url": entry.get("url"),
                "data_type": entry.get("data_type"),
                "date": entry.get("date", ""),
            }
            inventory_list.append(item)

        if self.format == "json":
            print(json.dumps(inventory_list, indent=2))

        elif self.format == "csv":
            output = StringIO()
            if inventory_list:
                keys = inventory_list[0].keys()
                writer = csv.DictWriter(output, fieldnames=keys)
                writer.writeheader()
                writer.writerows(inventory_list)
            print(output.getvalue())

        return entries
