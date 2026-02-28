#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.presets
~~~~~~~~~~~~~

Preset 'hook' macros.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import copy
import logging

from . import config
from . import utils

# example presets.json
# {
#   "presets": {
#     "archive-ready": {
#       "help": "Checksum, Enrich, Audit, and save to archive.log",
#       "hooks": [
#         {"name": "checksum", "args": {"algo": "sha256"}},
#         {"name": "enrich"},
#         {"name": "audit", "args": {"file": "archive_log.json"}}
#       ]
#     },
# }

logger = logging.getLogger(__name__)

_GLOBAL_PRESETS = {}
_MODULE_PRESETS = {}


def load_user_presets():
    """Load presets from the user's config file."""

    try:
        # Expected config structure:
        # {
        #   "presets": { "name": {...} },
        #   "modules": { "mod_name": { "presets": { "name": {...} } } }
        # }
        data = config.load_user_config("presets")
        return data.get("presets", {})
    except Exception as exception:
        logger.warning(f"Could not load user presets: {exception}")
        return {}


def hook_list_from_preset(preset_def):
    """Convert JSON definition to list of Hook Objects."""

    from fetchez.hooks.registry import HookRegistry

    hooks = []
    for h_def in preset_def.get("hooks", []):
        name = h_def.get("name")
        kwargs = h_def.get("args", {})

        # Instantiate using the Registry
        hook_cls = HookRegistry.get_hook(name)
        if hook_cls:
            try:
                hooks.append(hook_cls(**kwargs))
            except Exception as exception:
                logger.error(f"Failed to init preset hook '{name}': {exception}")
        else:
            logger.warning(f"Preset hook '{name}' not found.")

    return hooks


def register_global_preset(name, help_text, hooks):
    """Register a global CLI preset (e.g., --audit).
    These are available for ALL modules.
    """

    if name in _GLOBAL_PRESETS:
        logger.warning(f"Overwriting global preset '{name}'")

    _GLOBAL_PRESETS[name] = {"help": help_text, "hooks": hooks}
    logger.debug(f"Registered global preset: --{name}")


def register_module_preset(module, name, help_text, hooks):
    """Register a module-specific preset (e.g., --extract for multibeam).
    These only appear when running that specific module.

    Args:
        module (str): The module key (e.g., 'multibeam').
        name (str): The flag name (e.g., 'extract').
        help_text (str): Description.
        hooks (list): List of hook configurations.
    """

    if module not in _MODULE_PRESETS:
        _MODULE_PRESETS[module] = {}

    if name in _MODULE_PRESETS[module]:
        logger.warning(f"Overwriting preset '{name}' for module '{module}'")

    _MODULE_PRESETS[module][name] = {"help": help_text, "hooks": hooks}
    logger.debug(f"Registered preset --{name} for module {module}")


def get_module_presets(module_name):
    """Return presets registered for a specific module,
    PLUS any global presets that don't conflict.
    """

    # Start with global
    available = _GLOBAL_PRESETS.copy()

    # Overlay module specific ones (they take precedence)
    if module_name in _MODULE_PRESETS:
        mod_specific = _MODULE_PRESETS[module_name]
        available.update(mod_specific)

    return available


def get_global_presets():
    """Return combined user presets AND plugin presets."""

    all_presets = _GLOBAL_PRESETS.copy()
    user_presets = load_user_presets()
    all_presets.update(user_presets)

    return all_presets


# maybe we have it init actual presets?
def init_current_presets():
    """Export the CURRENT active presets (built-ins + loaded plugins) to a JSON file."""

    import yaml

    output_filename = "fetchez_presets_template.yaml"
    output_path = os.path.abspath(output_filename)

    if os.path.exists(output_path):
        logger.warning(f"File already exists: {output_path}")
        logger.warning("Please remove or rename it to generate a fresh template.")
        return

    export_data = {"presets": copy.deepcopy(_GLOBAL_PRESETS), "modules": {}}

    for mod_name, presets_dict in _MODULE_PRESETS.items():
        export_data["modules"][mod_name] = {"presets": copy.deepcopy(presets_dict)}

    try:
        with open(output_path, "w") as f:
            yaml.dump(export_data, f, sort_keys=False, default_flow_style=False)

        print(f"{utils.GREEN}✅ Exported active presets to: {utils.RESET}{output_path}")
        print("\nTo use these as your personal defaults:")
        print("  1. Edit the file to customize your workflows.")
        print(f"  2. Move it to: {utils.CYAN}~/.fetchez/presets.yaml{utils.RESET}")
        print("     (Or merge it into your existing config.yaml)")

    except Exception as exception:
        logger.error(f"Failed to export presets: {exception}")


def init_presets():
    """Generate a default presets.json file."""

    import yaml

    config_dir = config.CONFIG_PATH
    config_file = os.path.join(config_dir, "presets.yaml")

    if os.path.exists(config_file):
        print(f"Config file already exists at: {config_file}")
        return

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    default_config = {
        "presets": {
            "audit-full": {
                "help": "Generate SHA256 hashes, enrichment, and a full JSON audit log.",
                "hooks": [
                    {"name": "checksum", "args": {"algo": "sha256"}},
                    {"name": "enrich"},
                    {"name": "audit", "args": {"file": "audit_full.json"}},
                ],
            },
            "clean-download": {
                "help": "Unzip files and remove the original archive.",
                "hooks": [{"name": "unzip", "args": {"remove": "true"}}],
            },
        },
        "modules": {
            "multibeam": {
                "presets": {
                    "inf_only": {
                        "help": "multibeam Only: Fetch only inf files",
                        "hooks": [
                            {
                                "name": "filename_filter",
                                "args": {"match": ".inf", "stage": "pre"},
                            },
                        ],
                    }
                }
            }
        },
    }

    try:
        with open(config_file, "w") as f:
            f.write("# Fetchez User Configuration & Presets\n")
            f.write("# Define your custom workflow macros here.\n\n")
            yaml.dump(default_config, f, sort_keys=False, default_flow_style=False)

        logger.info(f"Created default configuration at: {config_file}")
        logger.info("Edit this file to add your own workflow presets.")
    except Exception as e:
        logger.error(f"Could not create presets config: {e}")
