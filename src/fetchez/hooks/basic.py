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
from io import StringIO

from . import FetchHook
from .. import utils

logger = logging.getLogger(__name__)

PRINT_LOCK = threading.Lock()

class PipeOutput(FetchHook):
    name = "pipe"
    desc = "Print absolute file paths to stdout for piping."
    stage = 'post'

    def run(self, entries):
        """Input is: [url, path, type, status]"""

        for entry in entries:
            if entry.get('status') == 0:
                with PRINT_LOCK:
                    print(os.path.abspath(entry.get('dst_fn')), file=sys.stdout, flush=True)
        return entries


class DryRun(FetchHook):
    name = "dryrun"
    desc = "Clear the download queue (simulate only)."
    stage = 'pre'
    
    def run(self, entries):
        # Return empty list to stop execution
        return []

    
class ListEntries(FetchHook):
    name = "list"
    desc = "Print discovered URLs to stdout."
    stage = 'pre'

    def run(self, entries):
        for mod, entry in entries:
            print(entry.get('url', ''))
        return entries

    
class PreInventory(FetchHook):
    name = "pre_inventory"
    desc = "Output metadata inventory (JSON/CSV). Usage: --hook inventory:format=csv"
    stage = 'pre'
    
    def __init__(self, format='json', **kwargs):
        super().__init__(**kwargs)
        self.format = format.lower()

        
    def run(self, entries):
        # Convert (mod, entry) tuples to flat dicts for reporting
        inventory_list = []
        for mod, entry in entries:
            item = {
                'module': mod.name,
                'filename': entry.get('dst_fn'),
                'url': entry.get('url'),
                'data_type': entry.get('data_type'),
                'date': entry.get('date', ''),
            }
            inventory_list.append(item)

        if self.format == 'json':
            print(json.dumps(inventory_list, indent=2))
            
        elif self.format == 'csv':
            output = StringIO()
            if inventory_list:
                keys = inventory_list[0].keys()
                writer = csv.DictWriter(output, fieldnames=keys)
                writer.writeheader()
                writer.writerows(inventory_list)
            print(output.getvalue())
            
        return entries # Return unmodified    


class Inventory(FetchHook):
    name = "inventory"
    desc = "Output metadata inventory (JSON/CSV). Usage: --hook inventory:format=csv"
    stage = 'post'
    
    def __init__(self, format='json', **kwargs):
        super().__init__(**kwargs)
        self.format = format.lower()

        
    def run(self, entries):
        # Convert (mod, entry) tuples to flat dicts for reporting
        inventory_list = []
        for entry in entries:
            # item = {
            #     'module': mod.name,
            #     'filename': entry.get('dst_fn'),
            #     'url': entry.get('url'),
            #     'data_type': entry.get('data_type'),
            #     'date': entry.get('date', ''),
            # }
            inventory_list.append(entry)

        if self.format == 'json':
            print(json.dumps(inventory_list, indent=2))
            
        elif self.format == 'csv':
            output = StringIO()
            if inventory_list:
                keys = inventory_list[0].keys()
                writer = csv.DictWriter(output, fieldnames=keys)
                writer.writeheader()
                writer.writerows(inventory_list)
            print(output.getvalue())
            
        return entries # Return unmodified    


class Audit(FetchHook):
    """Write a summary of all operations to a log file."""
    
    name = "audit"
    desc = "Save a run summary to a file. Usage: --hook audit:file=log.json"
    stage = 'post'

    def __init__(self, file='audit.json', format='json', **kwargs):
        super().__init__(**kwargs)
        self.filename = file
        self.format = format.lower()

        
    def run(self, all_results):
        # all_results is a list of dicts: [{'url':..., 'dst_fn':..., 'status':...}, ...]
        
        if not all_results:
            return

        try:
            with open(self.filename, 'w') as f:
                if self.format == 'json':
                    json.dump(all_results, f, indent=2)
                    
                elif self.format == 'csv':
                    keys = all_results[0].keys()
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(all_results)
                    
                else:
                    for res in all_results:
                        status = "OK" if res.get('status') == 0 else "FAIL"
                        f.write(f"[{status}] {res.get('dst_fn')} < {res.get('url')}\n")
                        
            print(f"Audit log written to {self.filename}")
            
        except Exception as e:
            print(f"Failed to write audit log: {e}")


class FilenameFilter(FetchHook):
    """Filter the pipeline results by filename pattern."""
    
    name = "filename_filter"
    desc = "Filter results by filename. Usage: --hook filter:match=.tif"
    stage = 'file'

    def __init__(self, match=None, exclude=None, regex=False, **kwargs):
        """Args:
            match (str): Keep only files containing this string.
            exclude (str): Discard files containing this string.
            regex (bool): Treat match/exclude strings as regex patterns.
        """
        
        super().__init__(**kwargs)
        self.match = utils.str_or(match)
        self.exclude = utils.str_or(exclude)
        self.regex = regex

        
    def run(self, entries):
        # Input: List of file entries
        # Output: Filtered list of file entries
        
        kept_entries = []
        
        for entry in entries:
            local_path = entry.get('dst_fn', '')
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
                kept_entries.append(entry)
                
        return kept_entries    
