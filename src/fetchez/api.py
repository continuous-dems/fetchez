#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.api
~~~~~~~~~~~
High-level Python Interface for Fetchez.

Usage:
    import fetchez

    # Search
    fetchez.search("bathymetry")

    # Get Data (Returns list of local file paths)
    files = fetchez.get("nos_hydro", region=[-120, -118, 33, 34], year=2020)

    # Advanced (With Hooks)
    files = fetchez.get("blue_topo", hooks=['unzip', 'filter:match=.tif'])
"""

import os
import logging
from typing import List, Optional

from .core import run_fetchez
from .registry import FetchezRegistry
from .hooks.registry import HookRegistry
from .spatial import parse_region
# from .cli import setup_logging

logger = logging.getLogger(__name__)


def search(term: Optional[str] = None) -> None:
    """Search available modules by tag, description, or name."""

    FetchezRegistry.load_user_plugins()
    FetchezRegistry.load_installed_plugins()

    if not term:
        print("\nAvailable Modules:")
        for key, meta in FetchezRegistry._modules.items():
            if isinstance(meta, dict):
                print(f" - {key}: {meta.get('desc', '')}")
        return

    results = FetchezRegistry.search_modules(term)
    if not results:
        print(f"No modules found for '{term}'")
        return

    print(f"\nSearch results for '{term}':")
    for mod_key in results:
        meta = FetchezRegistry.get_info(mod_key)
        print(
            f" - {mod_key}: {meta.get('desc', 'N/A')} [{meta.get('agency', 'Unknown')}]"
        )


def get(
    module: str,
    region: Optional[List[float] | str] = None,
    outdir: Optional[str] = None,
    threads: int = 4,
    hooks: Optional[List[str]] = None,
    **kwargs,
) -> List[str]:
    """Fetch data from a module in one line.

    Args:
        module (str): Module name (e.g., 'nos_hydro', 'tnm').
        region (list/str): [W, E, S, N] or 'loc:Boulder'.
        outdir (str): Where to save files (default: ./<module>).
        threads (int): Parallel download threads.
        hooks (list): List of hook strings (e.g. ['unzip', 'audit']).
        **kwargs: Arguments passed directly to the module (year=..., datatype=...).

    Returns:
        List[str]: A list of absolute paths to the downloaded files.
    """

    FetchezRegistry.load_user_plugins()
    FetchezRegistry.load_installed_plugins()
    HookRegistry.load_builtins()

    ModCls = FetchezRegistry.load_module(module)
    if not ModCls:
        raise ValueError(f"Unknown module: {module}")

    src_region = parse_region(region)[0] if region else None

    active_hooks = []
    if hooks:
        for h_str in hooks:
            name, h_kwargs = _parse_hook_string(h_str)
            HookCls = HookRegistry.get_hook(name)
            if HookCls:
                active_hooks.append(HookCls(**h_kwargs))
            else:
                logger.warning(f"Hook '{name}' not found. Skipping.")

    try:
        mod_instance = ModCls(
            src_region=src_region, hook=active_hooks, outdir=outdir, **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to initialize {module}: {e}")
        return []

    logger.info(f"Querying {module}...")
    try:
        mod_instance.run()
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return []

    if not mod_instance.results:
        logger.warning(f"No results found for {module} with given parameters.")
        return []

    run_fetchez([mod_instance], threads=threads)

    downloaded_files = []
    for entry in mod_instance.results:
        if entry.get("status") == 0:
            fn = entry.get("dst_fn")
            if fn and os.path.exists(fn):
                downloaded_files.append(os.path.abspath(fn))

    return downloaded_files


def _parse_hook_string(h_str):
    """Helper to parse 'hook:arg=val' strings."""

    if ":" in h_str:
        name, rest = h_str.split(":", 1)
        parts = rest.split(",")
    else:
        name = h_str
        parts = []

    kwargs = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            # Simple type inference
            if v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            else:
                try:
                    if "." in v:
                        v = float(v)
                    else:
                        v = int(v)
                except Exception:
                    pass
            kwargs[k] = v
        else:
            kwargs[p] = True
    return name, kwargs
