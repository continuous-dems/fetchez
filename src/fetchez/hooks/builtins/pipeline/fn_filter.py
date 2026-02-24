#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.pipeline.fn_filter
~~~~~~~~~~~~~

Filter the filenames to be used in the pipeline.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import re
import logging

from fetchez import utils
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class FilenameFilter(FetchHook):
    """Filter the pipeline results by filename pattern."""

    name = "filename_filter"
    desc = "Filter results by filename. Usage: --hook filter:match=.tif"
    stage = "file"
    category = "pipeline"

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

        # logger.info(f"filename_filter is set to stage {self.stage}")

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

        # if self.stage == "pre":
        #     logger.info(
        #         f"Filename Filter hook filtered files and has kept {len(kept_entries)} matches."
        #     )
        return kept_entries
