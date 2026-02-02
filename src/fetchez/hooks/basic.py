import sys
import json
import os
import threading
from io import StringIO
from . import FetchHook

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
