#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.__init__
~~~~~~~~~~~~~

This init file also holds the FetchHook super class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

class FetchHook:
    """Base class for all Fetchez Hooks."""
    
    # Unique identifier for CLI (e.g., --hook unzip)
    name = "base_hook"
    # Description for --list-hooks
    desc = "Does nothing."
    # Defaults to 'file', but could be 'pre_fetch' or 'post_fetch'
    # 'pre':  Runs once before any downloads start.
    # 'file': Runs in the worker thread immediately after a file download.
    # 'post': Runs once after all downloads are finished.
    stage = 'file' 

    def __init__(self, **kwargs):
        self.opts = kwargs

    def run(self, entry):
        """Execute the hook.
        
        Args:
            entry: For 'file' stage: [url, path, type, status]
                   For 'pre'/'post': The full list of results (so far) or context.
        
        Returns:
            Modified entry (for 'file' stage pipeline) or None.
        """
        
        return entry
