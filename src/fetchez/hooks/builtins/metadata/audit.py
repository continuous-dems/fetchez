#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.metadata.audit
~~~~~~~~~~~~~

Post-fetchez audit (summary of all operations, etc)

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import csv
import logging

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Audit(FetchHook):
    """Write a summary of all operations to a log file."""

    name = "audit"
    desc = "Save a run summary to a file. Usage: --hook audit:file=log.json"
    stage = "post"
    category = "metadata"

    def __init__(self, file="audit.json", format="json", **kwargs):
        super().__init__(**kwargs)
        self.filename = file
        self.format = format.lower()

    def _sanitize(self, entry):
        """Remove or stringify non-serializable objects like generators."""

        clean = {}
        for k, v in entry.items():
            if k in ['stream', 'array_yield']:
                continue

            if isinstance(v, (dict, list, str, int, float, bool, type(None))):
                clean[k] = v
            else:
                clean[k] = str(v)
        return clean

    def run(self, all_results):
        # all_results is a list of dicts: [{'url':..., 'dst_fn':..., 'status':...}, ...]

        if not all_results:
            return

        try:
            entry_results = [self._sanitize(e) for m, e in all_results]
            # entry_results = [e for m, e in all_results]
            with open(self.filename, "w") as f:
                if self.format == "json":
                    json.dump(entry_results, f, indent=2)

                elif self.format == "csv":
                    keys = set().union(*(d.keys() for d in entry_results))
                    # keys = all_results[0].keys()
                    # writer = csv.DictWriter(f, fieldnames=keys)
                    writer = csv.DictWriter(f, fieldnames=sorted(list(keys)))
                    writer.writeheader()
                    writer.writerows(entry_results)

                else:
                    for res in entry_results:
                        status = "OK" if res.get("status") == 0 else "FAIL"
                        f.write(f"[{status}] {res.get('dst_fn')} < {res.get('url')}\n")

            print(f"Audit log written to {self.filename}")

        except Exception as e:
            print(f"Failed to write audit log: {e}")

        return all_results
