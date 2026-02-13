#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.checkpoints_3dep
~~~~~~~~~~~~~

3DEP elevation checkpoints

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from typing import Optional, List, Any

from fetchez import core
from fetchez import cli

CHECKPOINTS_3DEP_URL = 'https://www.sciencebase.gov/catalog/file/get/67075e6bd34e969edc59c3e7?f=__disk__80%2F12%2F9e%2F80129e86d18461ed921b288f13e08c62e8590ffb'
REFERER = 'https://www.sciencebase.gov/vocab/category/item/identifier'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'referer': REFERER
}


@cli.cli_opts(help_text="USGS 3DEP Elevation Checkpoints")
class CheckPoints3DEP(core.FetchModule):
    def __init__(self, **kwargs):
        super().__init__(name='3dep_cp', **kwargs)
        self.headers = HEADERS

    def run(self):
        self.add_entry_to_results(
            url=CHECKPOINTS_3DEP_URL,
            dst_fn='CheckPoints_3DEP.zip',
            data_type='checkpoints',
            agency='USGS',
            title='3DEP Elevation Checkpoints',
            region='USA',
            format='Shapefile (zipped)',
            license='Public Domain'
        )
