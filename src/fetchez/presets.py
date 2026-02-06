#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.core
~~~~~~~~~~~~~

Preset 'hook' macros.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging

from . import config

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

#home_dir = os.path.expanduser('~')
#CONFIG_PATH = os.path.join(home_dir, '.fetchez', 'presets.json')
_GLOBAL_PRESETS = {}
# Structure: { 'module_name': { 'preset_name': { 'help': ..., 'hooks': ... } } }
_MODULE_PRESETS = {}

logger = logging.getLogger(__name__)    

def load_user_presets():
    """Load presets from the user's config file."""

    try:
        data = config.load_user_config()
        return data.get('presets', {})
    except:
        logger.warning(f'Could not load presets: {e}') 
        return {}

    
def hook_list_from_preset(preset_def):
    """Convert JSON definition to list of Hook Objects."""
    
    from fetchez.hooks.registry import HookRegistry
    
    hooks = []
    for h_def in preset_def.get('hooks', []):
        name = h_def.get('name')
        kwargs = h_def.get('args', {})
        
        # Instantiate using the Registry
        hook_cls = HookRegistry.get_hook(name)
        if hook_cls:
            hooks.append(hook_cls(**kwargs))
            
    return hooks

# fetchez/src/fetchez/presets.py

import logging

logger = logging.getLogger(__name__)

# Global presets (appear in main --help)
_GLOBAL_PRESETS = {}

# Module-specific presets (appear in module-specific --help)
# Structure: { 'module_name': { 'preset_name': { 'help': ..., 'hooks': ... } } }
_MODULE_PRESETS = {}

def register_global_preset(name, help_text, hooks):
    """Register a global CLI preset (e.g., --audit).
    These are available for ALL modules.
    """
    
    if name in _GLOBAL_PRESETS:
        logger.warning(f"Overwriting global preset '{name}'")
        
    _GLOBAL_PRESETS[name] = {
        'help': help_text,
        'hooks': hooks
    }
    logger.debug(f"Registered global preset: --{name}")

    
def register_module_preset(module, name, help_text, hooks):
    """
    Register a module-specific preset (e.g., --extract for multibeam).
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

    _MODULE_PRESETS[module][name] = {
        'help': help_text,
        'hooks': hooks
    }
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


def init_presets():
    """Generate a default presets.json file."""
    
    from . import presets
    
    config_dir = config.CONFIG_PATH
    config_file = os.path.join(config_dir, 'presets.json')
    
    if os.path.exists(config_file):
        print(f'Config file already exists at: {config_file}')
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
                    {"name": "audit", "args": {"file": "audit_full.json"}}
                ]
            },
            "clean-download": {
                "help": "Unzip files and remove the original archive.",
                "hooks": [
                    {"name": "unzip", "args": {"remove": 'true'}}
                ]
            },
        },
        "modules": {
            "multibeam": {
                "presets": {
                    "inf_only": {
                        "help": "multibeam Only: Fetch only inf files",
                        "hooks": [
                            {"name": "filename_filter", "args": {"match": ".inf", "stage": "pre"}},
                        ]
                    }
                }
            }
        }
    }

    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info(f'Created default configuration at: {config_file}')
        logger.info('Edit this file to add your own workflow presets.')
    except Exception as e:
        logger.error(f'Could not create presets config: {e}')

