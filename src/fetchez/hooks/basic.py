#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.basic
~~~~~~~~~~~~~

This holds the basic fetchez hooks. These are default
standard hooks.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import json
import csv
import re
import logging
import threading
import hashlib
import mimetypes
from datetime import datetime
from io import StringIO

from . import FetchHook
from .. import utils

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()


class PipeOutput(FetchHook):
    name = "pipe"
    desc = "Print absolute file paths to stdout for piping."
    stage = "post"
    category = "pipeline"

    def run(self, entries):
        """Input is: [url, path, type, status]"""

        for mod, entry in entries:
            if entry.get("status") == 0:
                with PRINT_LOCK:
                    print(
                        os.path.abspath(entry.get("dst_fn")),
                        file=sys.stdout,
                        flush=True,
                    )
        return entries


class DryRun(FetchHook):
    name = "dryrun"
    desc = "Clear the download queue (simulate only)."
    stage = "pre"
    category = "pipeline"

    def run(self, entries):
        # Return empty list to stop execution
        return []


class ListEntries(FetchHook):
    name = "list"
    desc = "Print discovered URLs to stdout."
    stage = "pre"
    category = "metadata"

    def run(self, entries):
        for mod, entry in entries:
            print(entry.get("url", ""))
        return entries


class Checksum(FetchHook):
    """Calculates file checksums immediately after download.

    Adds '{algo}_hash' and 'local_size' to the result dictionary.

    Usage: --hook checksum:algo=sha256
    """

    name = "checksum"
    desc = "Calculate file checksums (md5/sha1/sha256)."
    stage = "file"
    category = "metadata"

    def __init__(self, algo="md5", **kwargs):
        super().__init__(**kwargs)
        self.algo = algo.lower()
        if self.algo not in hashlib.algorithms_available:
            logger.warning(f"Checksum algo '{self.algo}' not found. Defaulting to md5.")
            self.algo = "md5"

    def run(self, entries):
        for mod, entry in entries:
            filepath = entry.get("dst_fn")

            if entry.get("status") != 0 or not os.path.exists(filepath):
                entry[f"{self.algo}_hash"] = None
                entry["local_size"] = 0
                continue

            try:
                hasher = hashlib.new(self.algo)
                size = 0
                with open(filepath, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                        size += len(chunk)

                entry[f"{self.algo}_hash"] = hasher.hexdigest()
                entry["local_size"] = size

                remote_size = entry.get("remote_size")
                if remote_size:
                    try:
                        if int(remote_size) != size:
                            logger.warning(
                                f"Size mismatch for {filepath}: {size} != {remote_size}"
                            )
                            entry["verification"] = "failed"
                        else:
                            entry["verification"] = "passed"
                    except ValueError:
                        pass  # remote_size might not be an int

            except Exception as e:
                logger.warning(f"Checksum failed for {filepath}: {e}")

        return entries


class MetadataEnrich(FetchHook):
    """Adds filesystem timestamps and mime-types to the result.

    Usage: --hook enrich
    """

    name = "enrich"
    desc = "Add file timestamps and mime-types to metadata."
    stage = "file"
    category = "metadata"

    def run(self, entries):
        for mod, entry in entries:
            filepath = entry.get("dst_fn")

            if entry.get("status") != 0 or not os.path.exists(filepath):
                continue

            try:
                stat = os.stat(filepath)
                entry["created_at"] = datetime.fromtimestamp(stat.st_ctime).isoformat()
                entry["modified_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat()

                mime, _ = mimetypes.guess_type(filepath)
                entry["mime_type"] = mime or "application/octet-stream"

            except Exception as e:
                logger.warning(f"Metadata enrichment failed for {filepath}: {e}")

        return entries


class Inventory(FetchHook):
    name = "pre_inventory"
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

    def run(self, all_results):
        # all_results is a list of dicts: [{'url':..., 'dst_fn':..., 'status':...}, ...]

        if not all_results:
            return

        try:
            entry_results = [e for m, e in all_results]
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


class FilenameFilter(FetchHook):
    """Filter the pipeline results by filename pattern."""

    name = "filename_filter"
    desc = "Filter results by filename. Usage: --hook filter:match=.tif"
    stage = "file"
    category = "file-op"

    def __init__(self, match=None, exclude=None, regex=False, stage=None, **kwargs):
        """Args:
        match (str): Keep only files containing this string.
        exclude (str): Discard files containing this string.
        regex (bool): Treat match/exclude strings as regex patterns.
        stage (str): Override hook stage ('pre', 'file', 'post').
        """

        super().__init__(**kwargs)
        self.match = utils.str_or(match)
        self.exclude = utils.str_or(exclude)
        self.regex = regex

        if stage:
            self.stage = (
                stage.lower() if stage.lower() in ["pre", "file", "post"] else "file"
            )

        logger.info(f"filename_filter is set to stage {self.stage}")

    def run(self, entries):
        # Input: List of file entries
        # Output: Filtered list of file entries

        kept_entries = []

        for item in entries:
            if isinstance(item, tuple):
                mod, entry = item
            else:
                entry = item

            local_path = entry.get("dst_fn", "")
            filename = os.path.basename(local_path)

            keep = True

            if self.match:
                if self.regex:
                    if not re.search(self.match, filename):
                        keep = False
                else:
                    if self.match not in filename:
                        keep = False

            if self.exclude and keep:
                if self.regex:
                    if re.search(self.exclude, filename):
                        keep = False
                else:
                    if self.exclude in filename:
                        keep = False

            if keep:
                kept_entries.append(item)

        logger.info(
            f"Filename Filter hook filtered files and has kept {len(kept_entries)} matches."
        )
        return kept_entries
