#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.project
~~~~~~~~~~~~~

Execute Project workflows defined in JSON or YAML files.

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

logger = logging.getLogger(__name__)


class ProjectRun:
    def __init__(self, config_file):
        self.config_file = config_file
        self.base_dir = os.path.dirname(os.path.abspath(config_file))
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from JSON or YAML."""

        if not os.path.exists(self.config_file):
            logger.error(f"Project file not found: {self.config_file}")
            return {}

        ext = os.path.splitext(self.config_file)[1].lower()

        try:
            with open(self.config_file, "r") as f:
                if ext in [".yaml", ".yml"]:
                    try:
                        import yaml

                        return yaml.safe_load(f)
                    except ImportError:
                        logger.error(
                            "PyYAML is missing. Install it to use .yaml files: pip install PyYAML"
                        )
                        return {}
                else:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse project file: {e}")
            return {}

    def _init_hooks(self, hook_defs):
        """Instantiate hooks from list of dicts."""

        if not hook_defs:
            return []

        active_hooks = []
        for h in hook_defs:
            name = h.get("name")
            kwargs = h.get("args", {})

            for k, v in kwargs.items():
                if isinstance(
                    v, str
                ):  # and k in ['file', 'output', 'output_grid', 'mask_fn', 'dem']:
                    if not os.path.isabs(v) and not v.startswith(
                        ("http", "s3://", "gs://", "ftp://")
                    ):
                        if "." in os.path.basename(v) or os.sep in v:
                            kwargs[k] = os.path.abspath(os.path.join(self.base_dir, v))

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

        # Global Settings
        project_meta = self.config.get("project", {})
        run_opts = self.config.get("execution", {})

        threads = run_opts.get("threads", 1)
        # verbose = run_opts.get("verbose", True)

        logger.info(f"Starting Project: {project_meta.get('name', 'Untitled')}")

        # Global Hooks
        global_hooks = self._init_hooks(self.config.get("global_hooks", []))

        # Global Region
        global_region_def = self.config.get("region")
        global_regions = (
            parse_region(global_region_def) if global_region_def else [None]
        )

        # Build Module Instances
        modules_to_run = []

        for mod_def in self.config.get("modules", []):
            mod_key = mod_def.get("module")
            mod_args = mod_def.get("args", {})
            mod_hooks = self._init_hooks(mod_def.get("hooks", []))

            # Module Region overrides Global
            mod_region_def = mod_def.get("region")
            if mod_region_def:
                mod_regions = parse_region(mod_region_def)
            else:
                mod_regions = global_regions

            if not mod_regions or mod_regions == [None]:
                logger.warning(f"Skipping module {mod_key}: No region defined.")
                continue

            ModCls = FetchezRegistry.load_module(mod_key)
            if not ModCls:
                logger.error(f"Unknown module: {mod_key}")
                continue

            for region in mod_regions:
                try:
                    instance = ModCls(src_region=region, hook=mod_hooks, **mod_args)
                    modules_to_run.append(instance)
                except Exception as e:
                    logger.error(f"Failed to init module {mod_key}: {e}")

        # Run
        if not modules_to_run:
            logger.warning("No valid modules to run.")
            return

        logger.info(f"Queued {len(modules_to_run)} jobs. Running...")

        for mod in modules_to_run:
            mod.run()

        run_fetchez(modules_to_run, threads=threads, global_hooks=global_hooks)
