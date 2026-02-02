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
        """Scan ~/.fetchez/hooks/ for python files."""
        
        home = os.path.expanduser("~")
        p_dir = os.path.join(home, ".fetchez", "hooks")
        
        if not os.path.exists(p_dir): return
        
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
    def _register_from_module(cls, module):
        """Inspect a module for classes inheriting from FetchHook."""
        
        import inspect
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, FetchHook) and obj is not FetchHook:
                key = getattr(obj, 'name', name.lower())
                cls._hooks[key] = obj

                
    @classmethod
    def get_hook(cls, name):
        return cls._hooks.get(name)
