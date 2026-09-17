#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.api
~~~~~~~~~~~
High-level Python Interface for Fetchez.

Usage::

    import fetchez

    # Search
    fetchez.search("bathymetry")

    # Get Data (Returns list of local file paths)
    files = fetchez.get("nos_hydro", region=[-120, -118, 33, 34], year=2020)

    # Advanced (With Hooks)
    files = fetchez.get("charts", region=[-120, -118, 33, 34], hooks=['unzip', 'filename_filter:match=.000'])

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from .streams.base import BaseStream
from .utils import parse_hook_string
from .core import run_fetchez
from .spatial import parse_region
from .recipe import Recipe
from .registry import (
    ModuleRegistry,
    BundleRegistry,
    HookRegistry,
    RecipeRegistry,
    SchemaRegistry,
    ModifierRegistry,
    PresetRegistry,
    StreamRegistry,
    ReaderRegistry,
    ProfileRegistry,
)

logger = logging.getLogger(__name__)


def _search_registry(registry_cls, term: Optional[str] = None) -> Dict[str, Any]:
    """Helper to load and search a specific registry."""

    registry_cls.load_all()
    full_reg = registry_cls.get_registry()

    if not term:
        return full_reg

    found = {}
    term_lower = term.lower()
    for name, meta in full_reg.items():
        desc = meta.get("desc", meta.get("desc", ""))
        tags = [t.lower() for t in meta.get("tags", [])]
        aliases = [a.lower() for a in meta.get("aliases", [])]
        category = meta.get("category", meta.get("category", ""))

        if (
            term_lower in name.lower()
            or term_lower in desc.lower()
            or term_lower in tags
            or term_lower in aliases
            or term_lower in category.lower()
        ):
            found[name] = meta

    return found


def list_modules() -> Dict[str, Any]:
    return _search_registry(ModuleRegistry)


def search_modules(term) -> Dict[str, Any]:
    return _search_registry(ModuleRegistry, term)


def list_bundles() -> Dict[str, Any]:
    return _search_registry(BundleRegistry)


def search_bundles(term) -> Dict[str, Any]:
    return _search_registry(BundleRegistry, term)


def list_hooks() -> Dict[str, Any]:
    return _search_registry(HookRegistry)


def search_hooks(term) -> Dict[str, Any]:
    return _search_registry(HookRegistry, term)


def list_recipes() -> Dict[str, Any]:
    return _search_registry(RecipeRegistry)


def search_recipes(term) -> Dict[str, Any]:
    return _search_registry(RecipeRegistry, term)


def list_schemas() -> Dict[str, Any]:
    return _search_registry(SchemaRegistry)


def search_schemas(term) -> Dict[str, Any]:
    return _search_registry(SchemaRegistry, term)


def list_modifiers() -> Dict[str, Any]:
    return _search_registry(ModifierRegistry)


def search_modifiers(term) -> Dict[str, Any]:
    return _search_registry(ModifierRegistry, term)


def list_presets() -> Dict[str, Any]:
    return _search_registry(PresetRegistry)


def search_presets(term) -> Dict[str, Any]:
    return _search_registry(PresetRegistry, term)


def list_streams() -> Dict[str, Any]:
    return _search_registry(StreamRegistry)


def search_streams(term) -> Dict[str, Any]:
    return _search_registry(StreamRegistry, term)


def list_readers() -> Dict[str, Any]:
    return _search_registry(ReaderRegistry)


def search_readers(term) -> Dict[str, Any]:
    return _search_registry(ReaderRegistry, term)


def list_profiles() -> Dict[str, Any]:
    return _search_registry(ProfileRegistry)


def search_profiles(term) -> Dict[str, Any]:
    return _search_registry(ProfileRegistry, term)


def search(term: str) -> Dict[str, Dict[str, Any]]:
    """Search across ALL Fetchez registries simultaneously."""
    return {
        "modules": _search_registry(ModuleRegistry, term),
        "bundles": _search_registry(BundleRegistry, term),
        "hooks": _search_registry(HookRegistry, term),
        "recipes": _search_registry(RecipeRegistry, term),
        "schemas": _search_registry(SchemaRegistry, term),
        "modifiers": _search_registry(ModifierRegistry, term),
        "presets": _search_registry(PresetRegistry, term),
        "streams": _search_registry(StreamRegistry, term),
        "readers": _search_registry(ReaderRegistry, term),
        "profiles": _search_registry(ProfileRegistry, term),
    }


def _compile_modules(sources, region=None, shared_cache=None, **kwargs) -> List[Any]:
    """Resolves strings/dicts into initialized FetchModules with local hooks."""

    if isinstance(sources, (str, dict)):
        sources = [sources]

    BundleRegistry.load_all()
    ModuleRegistry.load_all()
    PresetRegistry.load_all()
    HookRegistry.load_all()

    # Shared Cache
    abs_cache = None
    if shared_cache:
        abs_cache = Path(shared_cache).resolve()
        abs_cache.mkdir(parents=True, exist_ok=True)
        logger.info(f"Shared cache enabled: {abs_cache}")

    expanded_defs = BundleRegistry.expand_modules(sources)
    parsed_region = parse_region(region)[0] if region else None

    initialized_modules = []
    for mod_def in expanded_defs:
        mod_name = mod_def.get("module")
        mod_args = {**mod_def.get("args", {}), **kwargs}
        if abs_cache and mod_name not in [
            "file",
            "local_fs",
            "stdin",
        ]:
            mod_def.setdefault("args", {})["outdir"] = abs_cache

        raw_hooks = mod_def.get("hooks", [])
        expanded_hooks = PresetRegistry.expand_hooks(raw_hooks)

        active_mod_hooks = []
        for h_def in expanded_hooks:
            HookCls = HookRegistry.get_class(str(h_def.get("name")))
            if HookCls:
                active_mod_hooks.append(HookCls(**h_def.get("args", {})))

        ModCls = ModuleRegistry.get_class(str(mod_name))
        if not ModCls:
            ModCls = ModuleRegistry.get_class("local_fs")
            mod_args["path"] = mod_name

        initialized_modules.append(
            ModCls(src_region=parsed_region, hook=active_mod_hooks, **mod_args)
        )

    return initialized_modules


def get(
    module: str,
    region: Optional[List[float] | str] = None,
    region_srs: Optional[str] = "EPSG:4326",
    outdir: Optional[str | Path] = None,
    threads: int = 4,
    hooks: Optional[List[str]] = None,
    dry_run: bool = False,
    verbose: bool = True,
    ignore_failures: bool = False,
    **kwargs,
) -> List[str]:
    """Fetch data from a module in one line.

    Args:
        module: Module name (e.g., 'nos_hydro', 'tnm').
        region: [W, E, S, N] or 'loc:Boulder'.
        region_srs: The srs of the region (defalt: EPSG:4326).
        outdir: Where to save files (default: ./<module>).
        threads: Parallel download threads.
        hooks: List of hook strings (e.g. ['unzip', 'audit']).
        dry_run: Don't download any data.
        verbose: Run in verbose mode.
        ignore_failures: Ignore exceptions and push through.
        **kwargs: Arguments passed directly to the module (year=..., datatype=...).

    Returns:
        A list of absolute paths to the downloaded files.
    """

    from .recipe import setup_logging

    setup_logging(verbose)

    ModuleRegistry.load_all()
    HookRegistry.load_all()

    ModCls = ModuleRegistry.get_class(module)
    if not ModCls:
        raise ValueError(f"Unknown module: {module}")

    src_region = None
    if region:
        # If region is a string, append the CRS for the parser
        if isinstance(region, str):
            if "@" not in region and "," not in region:
                region = f"{region}@{region_srs}"
            parsed_regions = parse_region(region)
        else:
            parsed_regions = parse_region(region.copy())

        if parsed_regions:
            src_region = parsed_regions[0].copy()
            if not src_region.srs:
                src_region.srs = region_srs

    # src_region = parse_region(region)[0] if region else None
    # if src_region is not None and src_region.valid_p():
    #     src_region.srs = region_srs

    active_hooks = []
    if hooks:
        for h_str in hooks:
            if isinstance(h_str, str):
                hook_config = parse_hook_string(h_str)
            elif isinstance(h_str, dict):
                hook_config = h_str.copy()
            HookCls = HookRegistry.get_class(hook_config.get("name"))
            if HookCls:
                active_hooks.append(HookCls(**hook_config.get("args", {})))
            else:
                logger.warning(f"Hook {hook_config.get('name')} not found. Skipping.")

    try:
        mod_instance = ModCls(
            src_region=src_region, hook=active_hooks, outdir=outdir, **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to initialize {module}: {e}")
        return []

    logger.debug(f"Querying {module}...")
    try:
        mod_instance.run()
    except Exception as e:
        logger.exception(f"Query failed on {mod_instance}: {e}")
        return []

    if not mod_instance.results:
        logger.debug(f"No results found for {module} with given parameters.")
        return []

    if dry_run:
        manifest = []
        for _mod, entry in mod_instance.results:
            source = (
                entry.get("url") or entry.get("path") or entry.get("name") or str(entry)
            )
            manifest.append(source)

        if verbose:
            logger.info(f"DRY RUN: Found {len(manifest)} items to fetch.")
            for item in manifest:
                logger.info(f"  -> {item}")
        return manifest

    # Grab the final results from the fetchez pipeline
    final_results = run_fetchez(
        [mod_instance], threads=threads, ignore_failures=ignore_failures
    )

    downloaded_files = []
    for _mod, entry in final_results:  # mod_instance.results:
        if entry.get("status", 0) == 0:
            fn = entry.get("dst_fn")
            if fn and Path(fn).exists():
                downloaded_files.append(str(Path(fn).resolve()))

    return downloaded_files


def run_recipe(
    target: str,
    region: Optional[str] = None,
    region_srs: Optional[str] = "EPSG:4326",
    modifiers: Optional[List[str | Dict]] = None,
    schemas: Optional[List[str]] = None,
    ignore_failures: bool = False,
) -> bool:
    """Execute a YAML recipe.

    'target' can be a local file path or the name of a registered recipe.
    """

    import yaml
    from .recipe import Recipe

    RecipeRegistry.load_all()
    base_config = None

    if Path(target).exists():
        with open(target, "r", encoding="utf-8") as f:
            base_config = yaml.safe_load(f)
    else:
        recipe_meta = RecipeRegistry.get_recipe(target)
        if recipe_meta:
            base_config = recipe_meta["config"]
            logger.info(f"Loaded registered recipe: {target}")

    if not base_config:
        logger.error(f"Recipe '{target}' not found locally or in the registry.")
        return False

    if region:
        base_config["region"] = region

    if region_srs:
        base_config["region_srs"] = region_srs

    if modifiers:
        base_config["modifiers"] = base_config.get("modifiers", []) + modifiers
    if schemas:
        base_config["schemas"] = base_config.get("schemas", []) + schemas

    try:
        # Recipe.from_file(base_config).run()
        [r for r in Recipe(base_config).run(ignore_failures=ignore_failures)]
        return True
    except Exception as e:
        logger.error(f"Failed to run recipe '{target}': {e}")
        return False


class Pipeline:
    """A Builder class for orchestrating Fetchez workflows via the Recipe engine."""

    def __init__(self, sources, region=None, **kwargs):
        self.config = {
            "project": {"name": kwargs.get("name", "api_pipeline")},
            "region": region,
            "modules": sources if isinstance(sources, list) else [sources],
            "global_hooks": [],
        }

        self.kwargs = kwargs

    def modifier(self, **kwargs):
        pass

    def schema(self, **kwargs):
        pass

    def hook(self, hook_or_string, **kwargs):
        """Chain a global hook definition to the pipeline."""

        PresetRegistry.load_all()
        HookRegistry.load_all()

        if isinstance(hook_or_string, str):
            for h in hook_or_string:
                parsed_h = parse_hook_string(h)
                if parsed_h.get("name") in PresetRegistry.get_registry().keys():
                    parsed_h["preset"] = parsed_h.pop("name")
                elif parsed_h.get("name") not in HookRegistry.get_registry().keys():
                    raise ValueError(f"Hook or Preset '{h}' not found in the Registry!")
                self.config["global_hooks"].append(parsed_h)

        elif isinstance(hook_or_string, dict):
            if hook_or_string.get("name") or hook_or_string.get("preset"):
                self.config["global_hooks"].append(hook_or_string)
            else:
                raise ValueError(f"Invalid hook definition: {hook_or_string}.")
        else:
            raise ValueError(
                "Pipeline builder expects hook definitions (strings or dicts), "
                "not instantiated classes."
            )
        return self

    def execute(
        self, threads=4, shared_cache=None, ignore_failures=False, refresh=False
    ):
        """Execute the configured pipeline through the Recipe engine."""

        self.config["execution"] = {"threads": threads}

        return [
            r
            for r in Recipe.from_dict(self.config).run(
                shared_cache=shared_cache,
                refresh=refresh,
                ignore_failures=ignore_failures,
            )
        ]


def read(sources, region=None, shared_cache=None, **kwargs):
    """Initializes a Fetchez stream."""

    modules = _compile_modules(
        sources, region=region, shared_cache=shared_cache, **kwargs
    )
    parsed_region = parse_region(region)[0] if region else None

    return BaseStream(modules=modules, region=parsed_region)
