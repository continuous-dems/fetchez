#!/usr/bin/env python

"""
fetchez.hooks.transfer_log
~~~~~~~~~~~~~~~~~~~~~~~~~~

Generates a report of successful and failed downloads.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class TransferLog(FetchHook):
    """Write a summary of failed and successful downloads."""

    name = "transfer-log"
    meta_desc = "Generates a report of download successes and failures."
    meta_stage = "collection"  # post
    meta_category = "metadata"
    meta_aliases = ["transfer_log"]

    def __init__(self, file="download_report.txt", **kwargs):
        super().__init__(**kwargs)
        self.filename = file

    def run(self, entries):
        if not entries:
            return entries

        successes = []
        failures = []

        for _mod, entry in entries:
            # Status 0 indicates success in fetchez
            if entry.get("status", 0) == 0:
                successes.append(entry)
            else:
                failures.append(entry)

        try:
            with open(self.filename, "w") as f:
                f.write("=" * 80 + "\n")
                f.write("FETCHEZ DOWNLOAD TRANSFER REPORT\n")
                f.write("=" * 80 + "\n\n")

                # Put failures at the very top so they are impossible to miss!
                f.write(f"FAILED DOWNLOADS ({len(failures)}):\n")
                f.write("-" * 80 + "\n")
                if not failures:
                    f.write("  None! All files downloaded successfully.\n")
                else:
                    for entry in failures:
                        f.write(f"  [FAIL] {entry.get('url', 'Unknown URL')}\n")
                        f.write(f"         Target: {entry.get('dst_fn', 'Unknown')}\n")
                        f.write(f"         Module: {entry.get('name', 'Unknown')}\n")
                        f.write(
                            f"         Error: {entry.get('error_message', 'Unknown')}\n"
                        )

                f.write("\n" + "=" * 80 + "\n")
                f.write(f"SUCCESSFUL DOWNLOADS ({len(successes)}):\n")
                f.write("-" * 80 + "\n")
                for entry in successes:
                    f.write(f"  [OK] {os.path.basename(str(entry.get('dst_fn')))}\n")

            logger.info(f"Transfer log written to {self.filename}")

            if failures:
                logger.warning(
                    f"Pipeline finished with {len(failures)} failed downloads. Check {self.filename}."
                )

        except Exception as e:
            logger.error(f"Failed to write transfer log: {e}")

        return entries
