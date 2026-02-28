#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.recipe
~~~~~~~~~~~~~~
The Workflow Engine.
Loads a configuration (The Recipe) and executes it against the target region.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging

from .core import run_fetchez
from .spatial import parse_region
from .registry import FetchezRegistry
from .hooks.registry import HookRegistry
from .utils import TqdmLoggingHandler
from . import config
from . import presets
from . import __version__ as fetchez_version

logger = logging.getLogger(__name__)


def setup_logging(verbose=False):
    log_level = logging.INFO if verbose else logging.WARNING

    logger = logging.getLogger()
    logger.setLevel(log_level)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = TqdmLoggingHandler()
    formatter = logging.Formatter("[ %(levelname)s ] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _parse_version(v_str):
    """Dependency-free semantic version parser.
    Converts '2.1.0-beta' into (2, 1, 0).
    """

    parts = []
    for p in v_str.split("."):
        num = "".join(filter(str.isdigit, p))
        parts.append(int(num) if num else 0)
    return tuple(parts)


class Recipe:
    """The Workflow Orchestrator.

    Reads data ingestion and processing recipes from YAML/JSON files
    and executes them.

    Usage:
        # Load the Recipe
        recipe = Recipe.from_file("socal_project.yaml")

        # Run it.
        recipe.run()
    """

    def __init__(self, config, base_dir=None):
        self.config = config
        self.base_dir = base_dir or os.getcwd()
        self.name = self.config.get("project", {}).get("name", "Unnamed_Recipe")
        setup_logging(True)

    @classmethod
    def from_file(cls, config_source):
        """Factory method to load the Recipe.
        Accepts a filename (str) or a dictionary directly.
        """

        if isinstance(config_source, dict):
            return cls(config_source)

        if not os.path.exists(config_source):
            raise FileNotFoundError(f"Recipe not found: {config_source}")

        base_dir = os.path.dirname(os.path.abspath(config_source))
        ext = os.path.splitext(config_source)[1].lower()

        with open(config_source, "r") as f:
            if ext in [".yaml", ".yml"]:
                import yaml

                config = yaml.safe_load(f)
            else:
                config = json.load(f)

        return cls(config, base_dir=base_dir)

    def _check_integrity(self):
        """Ensures the fetchez version meets the recipe's minimum requirements."""

        conf = self.config.get("config", {})
        min_fz = conf.get("min_fetchez_version")

        if min_fz:
            current = _parse_version(fetchez_version)
            required = _parse_version(min_fz)
            if current < required:
                logger.error(
                    f"Recipe requires fetchez v{min_fz}, but found v{fetchez_version}"
                )
                raise RuntimeError("Fetchez version incompatibility.")

    def _resolve_path(self, path):
        """Resolves output paths relative to the recipe file."""

        if not isinstance(path, str):
            return path
        if path.startswith(("http", "s3://", "gs://", "ftp://")):
            return path
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.base_dir, path))

    def _init_hooks(self, hook_defs, mod=None):
        if not hook_defs:
            return []

        HookRegistry.load_builtins()
        hook_presets = presets.get_global_presets()
        hook_mod_presets = config.load_user_config("presets").get("modules", {})

        active_hooks = []
        for h in hook_defs:
            name = h.get("name")
            is_preset = h.get("preset")
            raw_kwargs = h.get("args", {})
            kwargs = {}
            for k, v in raw_kwargs.items():
                if k in [
                    "file",
                    "output",
                    "output_grid",
                    "mask_fn",
                    "dem",
                    "barrier",
                    "aux_path",
                    "path",
                ]:
                    kwargs[k] = self._resolve_path(v)
                else:
                    kwargs[k] = v

            # Check for global and mod-specific presets from ~/.fetchez/presets.yaml
            if is_preset:
                try:
                    hook_def = hook_presets.get(is_preset, {})
                    if hook_def:
                        chain = presets.hook_list_from_preset(hook_def)
                        active_hooks.extend(chain)
                    if mod:
                        mod_hooks = hook_mod_presets.get(mod, {}).get("presets", {})
                        hook_def = mod_hooks.get(is_preset, {})
                        if hook_def:
                            chain = presets.hook_list_from_preset(hook_def)
                            active_hooks.extend(chain)
                except Exception as e:
                    logger.error(f"could not load preset {is_preset} into the recipe.")
            else:
                HookCls = HookRegistry.get_hook(name)
                if HookCls:
                    active_hooks.append(HookCls(**kwargs))
                else:
                    logger.warning(f"Hook '{name}' missing.")

        return active_hooks

    def launch(self):
        """Alias for run() for backward compatibility."""

        self.launch()

    def run(self):
        """Execute the recipe!"""

        if not self.config:
            return

        self._check_integrity()
        logger.info(f"Preparing to execute recipe: {self.name}")

        run_opts = self.config.get("execution", {})
        threads = run_opts.get("threads", 1)

        global_hooks = self._init_hooks(self.config.get("global_hooks", []))
        global_region_def = self.config.get("region")
        global_regions = (
            parse_region(global_region_def) if global_region_def else [None]
        )

        modules_to_run = []
        for mod_def in self.config.get("modules", []):
            if isinstance(mod_def, str):
                mod_key, mod_args, mod_hooks, mod_region_def = mod_def, {}, [], None
            else:
                mod_key = mod_def.get("module")
                mod_args = mod_def.get("args", {})
                mod_hooks = self._init_hooks(mod_def.get("hooks", []), mod=mod_key)
                mod_region_def = mod_def.get("region")

            mod_regions = (
                parse_region(mod_region_def) if mod_region_def else global_regions
            )

            if not mod_regions or mod_regions == [None]:
                logger.warning(
                    f"Module '{mod_key}' has no target region. Skipping."
                )
                continue

            ModCls = FetchezRegistry.load_module(mod_key)
            if not ModCls:
                logger.error(f"Unknown module: {mod_key}")
                continue

            for region in mod_regions:
                if "path" in mod_args:
                    mod_args["path"] = self._resolve_path(mod_args["path"])

                try:
                    instance = ModCls(src_region=region, hook=mod_hooks, **mod_args)
                    modules_to_run.append(instance)
                except Exception as e:
                    logger.error(f"Failed to load {mod_key}: {e}")

        if not modules_to_run:
            logger.warning("Recipe empty. Nothing to execute.")
            return

        logger.info(
            f"Queued {len(modules_to_run)} module queries. Searching..."
        )
        for mod in modules_to_run:
            try:
                mod.run()
            except Exception as e:
                logger.error(
                    f"Module '{mod.name}' failed to generate URLs (Skipping): {e}"
                )

        run_fetchez(modules_to_run, threads=threads, global_hooks=global_hooks)
        logger.info(f"Recipe complete: {self.name}")
