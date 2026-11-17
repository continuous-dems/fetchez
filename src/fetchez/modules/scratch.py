#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.scratch
~~~~~~~~~~~~~~~~~~~~~~~

Scratch module.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


class Scratch(FetchModule):
    """Provide user-defined entries and runtime ownership.

    An execution may designate a Scratch instance as the
    runtime owner of derived entries that have no identifiable
    source module.

    This does not imply Scratch produced the underlying data.
    """

    name = "scratch"
    meta_category = "Generic"
    meta_desc = (
        "Provide manually defined entries and ownership "
        "for pipeline-generated artifacts."
    )
    meta_resolution = "N/A"
    meta_license = "N/A"

    def __init__(self, url=None, path=None, datatype=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.path = path
        self.datatype = datatype

    def run(self):
        if self.url and self.path and self.datatype:
            self.add_entry_to_results(self.url, self.path, self.datatype)
