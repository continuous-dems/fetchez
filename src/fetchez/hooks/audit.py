#!/usr/bin/env python

"""
fetchez.hooks.audit
~~~~~~~~~~~~~

Post-fetchez audit (summary of all operations, etc)

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import csv
import json
import logging
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Audit(FetchHook):
    """Write a summary of all operations to a log file.

    This outputs the fetch entry dictionary of each entry.
    """

    name = "audit"
    meta_desc = "Save a run summary of fetch entries to disk."
    meta_stage = "collection"
    meta_category = "metadata"

    def __init__(self, output="audit.json", out_format="json", **kwargs):
        super().__init__(**kwargs)
        self.output = output
        self.out_format = out_format.lower()

    def _sanitize(self, entry):
        """Remove or stringify non-serializable objects like generators."""

        clean = {}
        for key, val in entry.items():
            if key in ["stream"]:
                continue

            if isinstance(val, (dict, list, str, int, float, bool, type(None))):
                clean[key] = val
            else:
                clean[key] = str(val)
        return clean

    def run(self, entries):
        if entries:
            try:
                entry_results = [self._sanitize(entry) for mod, entry in entries]
                with open(self.output, "w") as f:
                    if self.out_format == "json":
                        json.dump(entry_results, f, indent=2)

                    elif self.out_format == "csv":
                        keys = set().union(*(d.keys() for d in entry_results))
                        writer = csv.DictWriter(f, fieldnames=sorted(list(keys)))
                        writer.writeheader()
                        writer.writerows(entry_results)

                    else:
                        for result in entry_results:
                            status = result.get("status")
                            if not status:
                                result["status"] = (
                                    0 if Path(result["dst_fn"]).exists() else -1
                                )

                            status = "OK" if result.get("status") == 0 else "FAIL"
                            f.write(
                                f"[{status}] {result.get('dst_fn')} < {result.get('url')}\n"
                            )

                logger.info(f"Audit log written to {self.output}")

            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")

        return entries
