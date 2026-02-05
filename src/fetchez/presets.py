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

def register_global_preset(name, help_text, hooks):
    """Register a global CLI preset from a plugin.
    
    Args:
        name (str): The flag name (e.g., 'make-shift-grid').
        help_text (str): Description for --help.
        hooks (list): List of dicts defining the hook chain.
    """
    
    _GLOBAL_PRESETS[name] = {
        'help': help_text,
        'hooks': hooks
    }

    
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

