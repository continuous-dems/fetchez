#!/usr/bin/env python

"""
fetchez.recipes.modifiers.exclude_module
~~~~~~~~~~~~~~~~

Recipe mutator to remove specifically named modules
from a recipe.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.recipes.modifiers.base import BaseModifier
from fetchez.utils import parse_arg_to_list

logger = logging.getLogger(__name__)


class ExcludeModuleModifier(BaseModifier):
    """Removes specific modules from a recipe config before execution.
    Useful for dropping problematic modules from large, pre-baked bundles.
    """

    name = "exclude_module"
    meta_desc = "Exclude specific modules from a recipe by name."

    def __init__(self, modules=None, **kwargs):
        super().__init__(**kwargs)

        self.excluded_modules = parse_arg_to_list(modules, str)

    def apply(self, config):
        """Mutates and returns the recipe config by removing excluded modules."""

        if not self.excluded_modules or "modules" not in config:
            return config

        original_count = len(config["modules"])
        filtered_modules = []

        for mod in config["modules"]:
            mod_name = None

            if isinstance(mod, str):
                mod_name = mod.split(":")[0].strip()

            elif isinstance(mod, dict):
                mod_name = mod.get("module", mod.get("bundle", "unknown")).strip()

            if mod_name and mod_name in self.excluded_modules:
                logger.info(f"[{self.name}]: Dropping module '{mod_name}' from recipe.")
            else:
                filtered_modules.append(mod)

        config["modules"] = filtered_modules

        dropped_count = original_count - len(filtered_modules)
        if dropped_count > 0:
            logger.debug(
                f"Excluded {dropped_count} modules. {len(filtered_modules)} remaining."
            )

        return config
