#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.registry
~~~~~~~~~~~~~

This holds the hook registry.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import importlib
import os
import sys
import logging
from . import FetchHook

logger = logging.getLogger(__name__)

class HookRegistry:
    _hooks = {}

    @classmethod
    def load_builtins(cls):
        """Load hooks shipped with fetchez (e.g., fetchez.hooks.basic)."""
        
        from . import basic, utils
        cls._register_from_module(basic)
        cls._register_from_module(utils)

        
    @classmethod
    def load_user_plugins(cls):
        """Scan ~/.fetchez/hooks/ and .fetchez/hooks for python files."""
        
        home = os.path.expanduser("~")
        home_hook_dir = os.path.join(home, ".fetchez", "hooks")
        cwd_hook_dir = os.path.join(home, ".fetchez", "hooks")

        for p_dir in [home_hook_dir, cwd_hook_dir]:
            if not os.path.exists(p_dir): continue

            sys.path.insert(0, p_dir)
            for f in os.listdir(p_dir):
                if f.endswith(".py") and not f.startswith("_"):
                    try:
                        mod_name = f[:-3]
                        mod = importlib.import_module(mod_name)
                        cls._register_from_module(mod)
                    except Exception as e:
                        logger.warning(f"Failed to load user hook {f}: {e}")
            sys.path.pop(0)


    @classmethod
    def register_hook(cls, hook_cls):
        """Register a hook class. 

        The hook must have a 'name' attribute (e.g. name='unzip').
        """

        import inspect
        if not hasattr(hook_cls, 'name'):
            logger.warning(f"Cannot register hook {hook_cls}: Missing 'name' attribute.")
            return

        key = hook_cls.name
        if inspect.isclass(hook_cls) and issubclass(hook_cls, FetchHook) and hook_cls is not FetchHook:            
            cls._hooks[key] = hook_cls
            logger.debug(f"Registered external hook: {key}")

        
    @classmethod
    def _register_from_module(cls, module):
        """Inspect a module for classes inheriting from FetchHook."""
        
        import inspect
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, FetchHook) and obj is not FetchHook:
                key = getattr(obj, 'name', name.lower())
                cls._hooks[key] = obj
                logger.debug(f"Registered hook from module: {key}")

                
    @classmethod
    def get_hook(cls, name):
        """Retrieve a hook class by name."""
        
        return cls._hooks.get(name)

    
    @classmethod
    def list_hooks(cls):
        """Return a dict of all registered hooks."""
        
        return cls._hooks
