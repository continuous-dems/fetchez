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
import logging

home_dir = os.path.expanduser('~')
CONFIG_PATH = os.path.join(home_dir, '.fetchez')

logger = logging.getLogger(__name__)

def load_user_config():
    """Load the user's config file."""

    config_json = os.path.join(CONFIG_PATH, 'presets.json')
    if not os.path.exists(config_json):
        return {}

    try:
        with open(config_json, 'r') as f:
            data = json.load(f)
            return data
    except Exception as e:
        logger.warning(f'Could not load config file: {e}')
        return {}
