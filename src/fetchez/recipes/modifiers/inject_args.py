#!/usr/bin/env python

"""
fetchez.recipes.modifiers.inject_args
~~~~~~~~~~~~~~~~

Recipe mutator to remove specifically named modules
from a recipe.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez.recipes.modifiers.base import BaseModifier

logger = logging.getLogger(__name__)


class InjectArgsModifier(BaseModifier):
    """Injects arbitrary key:value arguments into matching modules or hooks.
    Example: --modifier inject_args:match=stream_reproject,cache_dir=socal_data
    """

    name = "inject_args"
    meta_desc = "Injects arbitrary key:value arguments into matching modules or hooks."

    def __init__(self, match=None, **kwargs):
        super().__init__(**kwargs)
        self.match = match
        self.inject_kwargs = kwargs

    def _inject_into_item(self, item, match_name):
        """Helper to safely mutate string or dict-based definitions."""

        if isinstance(item, str) and item == match_name:
            if self.inject_kwargs:
                logger.info(
                    f"Modifier '{self.name}': Upgrading '{item}' to inject args."
                )
                return {item: self.inject_kwargs.copy()}
            return item

        if isinstance(item, dict):
            key = list(item.keys())[0]
            if key == match_name:
                val = item[key]
                if val is None:
                    val = {}
                elif isinstance(val, str):
                    val = {"_value": val}

                if isinstance(val, dict):
                    val.update(self.inject_kwargs)
                    logger.info(
                        f"Modifier '{self.name}': Injected {list(self.inject_kwargs.keys())} into '{key}'."
                    )
                item[key] = val

        return item

    def apply(self, config):
        """Mutates the recipe config by injecting arguments into matches."""

        if not self.match or not self.inject_kwargs:
            logger.warning(
                "InjectArgsModifier requires a 'match' target and arguments to inject. Skipping."
            )
            return config

        if "hooks" in config:
            config["hooks"] = [
                self._inject_into_item(h, self.match) for h in config["hooks"]
            ]

        if "modules" in config:
            updated_modules = []
            for mod in config["modules"]:
                mod = self._inject_into_item(mod, self.match)

                if isinstance(mod, dict):
                    mod_name = list(mod.keys())[0]
                    mod_args = mod[mod_name]
                    if isinstance(mod_args, dict) and "hooks" in mod_args:
                        mod_args["hooks"] = [
                            self._inject_into_item(h, self.match)
                            for h in mod_args["hooks"]
                        ]

                updated_modules.append(mod)
            config["modules"] = updated_modules

        return config
