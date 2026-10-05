#!/usr/bin/env python

"""
fetchez.recipes.modifiers
~~~~~~~~~~~~~~

Modifies the recipes region value by buffering it.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.recipes.modifiers import BaseModifier

logger = logging.getLogger(__name__)


class RegionBufferModifier(BaseModifier):
    name = "region-buffer"
    meta_desc = "Expands the target region by a specified amount or percentage."

    def __init__(self, buffer_val=None, buffer_pct=None, **kwargs):
        # Allow passing buffer_val=0.1 or buffer_pct=5
        self.buffer_val = float(buffer_val) if buffer_val is not None else None
        self.buffer_pct = float(buffer_pct) if buffer_pct is not None else None

    def apply(self, config):
        region = config.get("region")
        if not region:
            return config

        if self.buffer_val is None and self.buffer_pct is None:
            logger.warning(
                f"[{self.name}] No buffer_val or buffer_pct provided. Defaulting to 5% buffer."
            )
            self.buffer_pct = 5.0

        buffer_region = region.buffer(val=self.buffer_val, pct=self.buffer_pct)
        config["region"] = buffer_region.to_list()

        logger.info(f"[{self.name}] Applied buffer to region.")
        return config
