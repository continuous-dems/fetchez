#!/usr/bin/env python

"""
fetchez.recipes.schemas.validate_modules
~~~~~~~~~~~~~~

Schema to validate modules and hooks.
Checks that named modules and hooks exist in the registry.
Checks that their options are valid.
Checks for missing dependencies from specific Modules.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import inspect

from fetchez.registry import HookRegistry, ModuleRegistry

from .base import BaseSchema


def get_full_inheritance_parameters(cls):
    unique_params = {}

    # Iterate through the class inheritance chain (MRO)
    for base_class in cls.__mro__:
        # Skip the root 'object' class
        if base_class is object:
            continue

        # Only inspect if the class explicitly defines its own __init__
        if "__init__" in base_class.__dict__:
            sig = inspect.signature(base_class.__init__)

            for name, param in sig.parameters.items():
                # Filter out structural elements and wildcard unpackers (*args, **kwargs)
                if name == "self":
                    continue
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue

                # Keep the most specific definition (child overrides parent)
                if name not in unique_params:
                    unique_params[name] = param

    return unique_params


class CheckParams(BaseSchema):
    name = "validate-parameters"
    meta_desc = "validate the parameters for modules and hooks in the recipe."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def validate(self, config):
        """Validates the recipe for syntax, missing plugins, dependencies, and logical errors.

        Returns:
          bool: True if valid, False if errors exist.
          list: List of error messages.
        """

        ModuleRegistry.load_all()
        HookRegistry.load_all()

        # Validate Module Hooks
        for mod in config.get("modules", []):
            mod_name = mod.get("module")

            # Check Module-level Hooks
            for hook in mod.get("hooks", []):
                h_name = hook.get("name")
                h_args = hook.get("args", {})
                HookCls = HookRegistry.get_class(h_name)

                if not HookCls:
                    self.errors.append(
                        f"Missing Hook: '{h_name}' (in module {mod_name})"
                    )
                    continue

                params = get_full_inheritance_parameters(HookCls)
                for k, _v in h_args.items():
                    if k not in params:
                        self.errors.append(
                            f"[{mod_name} -> {h_name}] Possibly invalid parameter: {k}"
                        )

        # Validate Global Hooks
        for hook in config.get("global_hooks", []):
            h_name = hook.get("name")
            h_args = hook.get("args", {})
            HookCls = HookRegistry.get_class(h_name)

            if not HookCls:
                self.errors.append(f"Missing Global Hook: '{h_name}'")
                continue

            params = get_full_inheritance_parameters(HookCls)
            for k, _v in h_args.items():
                if k not in params:
                    self.errors.append(f"[{h_name}] Possibly invalid parameter: {k}")
