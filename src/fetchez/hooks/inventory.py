#!/usr/bin/env python

"""
fetchez.hooks.inventory
~~~~~~~~~~~~~

Generate an inventory (pre) of the fetchez operation.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import csv
import json
import logging

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Inventory(FetchHook):
    name = "inventory"
    meta_desc = "Output a metadata inventory (JSON/CSV)"
    meta_stage = "manifest"  # pre
    meta_category = "metadata"

    def __init__(self, output="inventory.json", out_format="json", **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.out_format = out_format.lower()

    def run(self, entries):
        if entries:
            inventory_list = []
            for mod, entry in entries:
                item = {
                    "module": mod.name,
                    "filename": entry.get("dst_fn"),
                    "url": entry.get("url"),
                    "data_type": entry.get("data_type"),
                    "date": entry.get("date", ""),
                }
                item.update(entry)
                inventory_list.append(item)

            with open(self.output, "w") as f:
                if self.out_format == "csv":
                    keys = set().union(*(d.keys() for d in inventory_list))
                    writer = csv.DictWriter(f, fieldnames=sorted(list(keys)))
                    writer.writeheader()
                    writer.writerows(inventory_list)
                else:
                    json.dump(inventory_list, f, indent=2)

            logger.info(f"Entry inventory written to {self.output}")

        return entries
