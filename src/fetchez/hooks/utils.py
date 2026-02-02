#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.utils
~~~~~~~~~~~~~

This holds the utiltiy fetchez hooks. These are default
standard hooks.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import zipfile
import logging
from . import FetchHook

logger = logging.getLogger(__name__)

class Unzip(FetchHook):
    """Automatically unzip files after download."""
    
    # Registry Metadata
    name = "unzip"
    desc = "Extract .zip archives. Usage: --hook unzip:remove=true:overwrite=false"
    stage = 'file'

    def __init__(self, remove=False, overwrite=False, **kwargs):
        """
        Args:
            remove (bool): Delete the original .zip file after extraction.
            overwrite (bool): Overwrite existing files.
        """
        super().__init__(**kwargs)
        self.remove = remove
        self.overwrite = overwrite

        
    def run(self, entries):
        out_entries = []
        for entry in entries:
            url = entry.get('url')
            zip_path = entry.get('dst_fn')
            dtype = entry.get('data_type')
            status = entry.get('status')

            if status != 0 or not zip_path.lower().endswith('.zip'):
                out_entries.append(entry)
                continue

            extract_dir = os.path.dirname(zip_path)

            try:
                with zipfile.ZipFile(zip_path, 'r') as z:
                    files_to_extract = [n for n in z.namelist() if not n.endswith('/')]

                    if not self.overwrite:
                        if all(os.path.exists(os.path.join(extract_dir, f)) for f in files_to_extract):
                            logger.info(f"Skipping unzip (files exist): {os.path.basename(zip_path)}")
                            out_entries.extend([{**entry, 'dst_fn': os.path.join(extract_dir, f), 'status': 0} for f in files_to_extract])
                            continue

                    z.extractall(extract_dir)

                    for fname in files_to_extract:
                        full_path = os.path.join(extract_dir, fname)
                        out_entries.append({**entry, 'dst_fn': full_path, 'status': 0})

                if self.remove:
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass

            except Exception as e:
                logger.error(f"Unzip failed for {zip_path}: {e}")
                out_entries.append(entry)

        return out_entries
        
