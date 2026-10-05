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

from fetchez.registry import HookRegistry, ModuleRegistry

from .base import BaseSchema


class CheckModules(BaseSchema):
    name = "validate-recipe"
    meta_desc = "validate the recipe for syntax, missing modules and hooks, and valid arguments."

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

        claimed_outputs = set()

        def check_output_collision(hook_dict, context_name):
            """Helper to check if a hook is clobbering an existing file."""

            out_file = hook_dict.get("args", {}).get("output")
            if out_file:
                if out_file in claimed_outputs:
                    self.errors.append(
                        f"[{context_name}] Output Collision: Multiple hooks are attempting to write to '{out_file}'."
                    )
                claimed_outputs.add(out_file)

        # Validate Modules
        for mod in config.get("modules", []):
            mod_name = mod.get("module")
            mod_keys = mod.keys()
            valid_keys = [
                "module",
                "bundle",
                "hooks",
                "args",
                "region",
                "region_srs",
                "description",
                "_comment",
            ]

            for key in mod_keys:
                if key not in valid_keys:
                    self.errors.append(
                        f"Module `{mod_name}` has unexpected reference to `{key}`"
                    )

            if not ModuleRegistry.get_class(mod_name) and mod_name not in [
                "file",
                "local_fs",
            ]:
                self.errors.append(f"Missing Module: '{mod_name}'")

            # Check Module-level Hooks
            # mod_hook_counts = {}
            for hook in mod.get("hooks", []):
                h_name = hook.get("name")
                HookCls = HookRegistry.get_class(h_name)

                if not HookCls:
                    self.errors.append(
                        f"Missing Hook: '{h_name}' (in module {mod_name})"
                    )
                    continue

                # Dependency Check
                if hasattr(HookCls, "_validate_deps"):
                    passed, msg = HookCls()._validate_deps()
                    if not passed:
                        self.errors.append(
                            f"[{mod_name} -> {h_name}] Missing Dependency: {msg}"
                        )

                check_output_collision(hook, f"Module: {mod_name}")

        # Validate Global Hooks
        # global_hook_counts = {}
        for hook in config.get("global_hooks", []):
            h_name = hook.get("name")
            HookCls = HookRegistry.get_class(h_name)

            if not HookCls:
                self.errors.append(f"Missing Global Hook: '{h_name}'")
                continue

            # Dependency Check
            if hasattr(HookCls, "_validate_deps"):
                passed, msg = HookCls()._validate_deps()
                if not passed:
                    self.errors.append(
                        f"[Global -> {h_name}] Missing Dependency: {msg}"
                    )

            check_output_collision(hook, "Global Hooks")
