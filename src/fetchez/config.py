#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.config
~~~~~~~~~~~~~

config file ~/.fetchez/ ...

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import yaml
import logging

home_dir = os.path.expanduser("~")
CONFIG_PATH = os.path.join(home_dir, ".fetchez")

logger = logging.getLogger(__name__)


def load_user_config(config_name):
    """Load the user's config file. Can be yaml or json."""

    exts = [".yaml", ".yml", ".json"]

    for ext in exts:
        config_file = os.path.join(CONFIG_PATH, config_name + ext)
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    if config_file.endswith(".json"):
                        return json.load(f)
                    else:
                        return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not load config file {config_file}: {e}")

    return {}
