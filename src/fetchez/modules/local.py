#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.local
~~~~~~~~~~~~~~~~~~~~~

Generic module to query custom/local FRED indices.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
from fetchez import core
from fetchez import cli
from fetchez import fred


@cli.cli_opts(
    help_text="Query a custom/local FRED index",
    index="Name or path of the FRED index (json) to load",
    mode=' "reference" (default) to point to existing files, or "copy" to stage them to outdir',
)
class Local(core.FetchModule):
    """Query a custom local spatial index.

    This module loads a user-defined FRED index (created via `fred.ingest`)
    and allows spatial querying of those files.
    """

    def __init__(self, index: str = None, mode: str = "reference", **kwargs):
        super().__init__(name="local", **kwargs)
        self.index_name = index
        self.mode = mode

    def run(self):
        if not self.index_name:
            return []

        # We check if it's a path, otherwise look in standard storage
        is_path = os.path.exists(self.index_name)
        idx = fred.FRED(self.index_name, local=is_path)

        # fred.search handles the spatial logic
        results = idx.search(region=self.region)

        for item in results:
            url = item.get("DataLink")

            # Handle destination filename
            if self.mode == "reference" and url.startswith("file://"):
                dst_fn = url[7:]
            else:
                dst_fn = os.path.basename(url)

            self.add_entry_to_results(
                url=url,
                dst_fn=dst_fn,
                data_type=item.get("DataType", "local"),
                agency=item.get("Agency", "Local"),
                title=item.get("Name", "Local File"),
            )

        return self
