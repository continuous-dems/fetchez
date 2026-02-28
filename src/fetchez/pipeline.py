#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.pipeline
~~~~~~~~~~~~~~~~
Execute workflows defined in JSON/YAML files or Python dictionaries.
Replaces the old 'project.py'.

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


class Pipeline:
    """Orchestrates the execution of a Fetchez workflow.

    Can be initialized from a file (CLI mode) or a dictionary (Script/Driver mode).

    Usage:
        # From File (CLI)
        Pipeline.from_file("my_project.yaml").run()

        # From Dict (Driver Script)
        config = {'modules': [...]}
        Pipeline(config).run()
    """

    def __init__(self, config, base_dir=None):
        self.config = config
        # If no base_dir provided (Dict mode), default to CWD
        self.base_dir = base_dir or os.getcwd()
        self.name = self.config.get("project", {}).get("name", "Untitled")
        setup_logging(True)

        FetchezRegistry.load_user_plugins()
        FetchezRegistry.load_installed_plugins()

        HookRegistry.load_builtins()
        HookRegistry.load_user_plugins()

    @classmethod
    def from_file(cls, config_file):
        """Factory method to load pipeline from a YAML/JSON file."""
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Project file not found: {config_file}")

        base_dir = os.path.dirname(os.path.abspath(config_file))
        config = cls._load_config_file(config_file)
        return cls(config, base_dir=base_dir)

    @staticmethod
    def _load_config_file(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        with open(filepath, "r") as f:
            if ext in [".yaml", ".yml"]:
                import yaml

                return yaml.safe_load(f)
            return json.load(f)

    def _resolve_path(self, path):
        """Resolves paths relative to the project file (base_dir)."""

        if not isinstance(path, str):
            return path
        if path.startswith(("http", "s3://", "gs://", "ftp://")):
            return path
        if os.path.isabs(path):
            return path

        return os.path.abspath(os.path.join(self.base_dir, path))

    def _init_hooks(self, hook_defs, mod=None):
        """Initialize hooks from list of dicts."""

        if not hook_defs:
            return []

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

            if is_preset:
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
            else:
                HookCls = HookRegistry.get_hook(name)
                if HookCls:
                    try:
                        active_hooks.append(HookCls(**kwargs))
                    except Exception as e:
                        logger.error(f"Failed to init hook {name}: {e}")
                else:
                    logger.warning(f"Hook '{name}' not found.")
        return active_hooks

    def run(self):
        """Build and execute the pipeline."""

        if not self.config:
            return

        logger.info(f"Starting Project: {self.name}")

        run_opts = self.config.get("execution", {})
        threads = run_opts.get("threads", 3)

        global_hooks = self._init_hooks(self.config.get("global_hooks", []))
        global_region_def = self.config.get("region")
        global_regions = (
            parse_region(global_region_def) if global_region_def else [None]
        )

        modules_to_run = []
        for mod_def in self.config.get("modules", []):
            if isinstance(mod_def, str):
                mod_key = mod_def
                mod_args = {}
                mod_hooks = []
                mod_region_def = None
            else:
                mod_key = mod_def.get("module")
                mod_args = mod_def.get("args", {})
                mod_hooks = self._init_hooks(mod_def.get("hooks", []), mod_key)
                mod_region_def = mod_def.get("region")

            mod_regions = (
                parse_region(mod_region_def) if mod_region_def else global_regions
            )

            if not mod_regions or mod_regions == [None]:
                logger.warning(f"Skipping module {mod_key}: No region defined.")
                continue

            ModCls = FetchezRegistry.load_module(mod_key)
            if not ModCls:
                logger.error(f"Unknown module: {mod_key}")
                continue

            for region in mod_regions:
                try:
                    if "path" in mod_args:
                        mod_args["path"] = self._resolve_path(mod_args["path"])

                    instance = ModCls(src_region=region, hook=mod_hooks, **mod_args)
                    modules_to_run.append(instance)
                except Exception as e:
                    logger.error(f"Failed to init module {mod_key}: {e}")

        if not modules_to_run:
            logger.warning("No valid modules to run.")
            return

        logger.info(f"Queued {len(modules_to_run)} jobs. Generating URLs...")
        for mod in modules_to_run:
            mod.run()

        run_fetchez(modules_to_run, threads=threads, global_hooks=global_hooks)
