#!/usr/bin/env python

"""
fetchez.hooks.fn_filter
~~~~~~~~~~~~~

Filter the filenames to be used in the pipeline.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import os
import re

from fetchez import utils
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class FilenameFilter(FetchHook):
    """Filter the entry by filename pattern."""

    name = "filename-filter"
    meta_desc = "Filter results by filename. Usage: --hook fn_filter:match=.tif"
    meta_stage = "file"
    meta_category = "pipeline"
    meta_aliases = ["filename_filter", "fn_filter"]

    def __init__(self, match=None, exclude=None, regex=False, **kwargs):
        """
        Args:
          match: Keep only files containing this string.
          exclude: Discard files containing this string.
          regex: Treat match/exclude strings as regex patterns.
        """

        super().__init__(**kwargs)
        self.match = utils.str_or(match)
        self.exclude = utils.str_or(exclude)
        self.regex = regex

        logger.debug(f"filename_filter is set to stage {self.stage}")

    def run(self, entries):
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

        if self.stage == "pre":
            logger.debug(
                f"Filename Filter hook filtered files from {mod} and has kept {len(kept_entries)} matches."
            )
        return kept_entries
