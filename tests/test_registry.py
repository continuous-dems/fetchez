# test_registry.py

import logging
import os
import ast

from pathlib import Path

import fetchez.modules
import fetchez.hooks
from fetchez.registry import (
    PluginRegistry,
    ModuleRegistry,
    HookRegistry,
    PresetRegistry,
)

# ReaderRegistry, ProfileRegistry, BundleRegistry, SchemaRegistry
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


def test_registry_integrity():
    """Ensure all core modules in the registry can be imported."""

    ModuleRegistry.load_builtins()
    modules = ModuleRegistry.get_registry()

    assert len(modules) > 0

    # Ensure we only test primary classes, not aliases
    primary_keys = [k for k, v in modules.items() if v.get("cls").lower() == k.lower()]

    for name in primary_keys:
        cls = ModuleRegistry.get_class(name)
        assert cls is not None, f"Failed to load class for {name}"
        assert hasattr(cls, "run"), f"Module {name} missing 'run' method"


def test_module_metadata_complete():
    """Ensure all core modules have the required metadata attributes defined."""

    ModuleRegistry.load_builtins()
    modules = ModuleRegistry.get_registry()

    # In the new registry, `meta_` is stripped from the keys in the dictionary.
    # New keys to be implemented:
    # ...
    required_keys = [
        "category",
        "desc",
        "agency",
        "tags",
        "resolution",
        "license",
        "urls",
    ]

    for name, meta in modules.items():
        if name in meta.get("aliases", []):
            continue  # Skip aliases

        missing = [attr for attr in required_keys if attr not in meta]
        assert not missing, f"Module '{name}' is missing metadata: {missing}"


def test_alias_resolution():
    ModuleRegistry.load_builtins()

    primary_cls = ModuleRegistry.get_class("lidarbc")
    alias_cls = ModuleRegistry.get_class("geobc")

    assert primary_cls is not None
    assert primary_cls is alias_cls


def test_optional_dependencies_are_protected():
    """Ensure all optional dependencies are imported inside a try/except block."""

    OPTIONAL_IMPORTS = {
        "boto3",
        "mercantile",
        "earthaccess",
        "pystac",
        "pystac_client",
        "planetary_computer",
        "copernicusmarine",
    }

    mod_dir = Path(fetchez.modules.__file__).parent
    hook_dir = Path(fetchez.hooks.__file__).parent

    unprotected_imports = []

    for directory in [mod_dir, hook_dir]:
        for root, _, files in os.walk(directory):
            for file in files:
                if not file.endswith(".py") or file.startswith("_"):
                    continue

                filepath = Path(root) / file
                with open(filepath, "r", encoding="utf-8") as f:
                    source = f.read()

                try:
                    tree = ast.parse(source, filename=str(filepath))
                except SyntaxError:
                    continue

                safe_lines = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Try):
                        safe_lines.update(range(node.lineno, node.end_lineno + 1))

                for node in ast.walk(tree):
                    imported_module = None

                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            base_mod = alias.name.split(".")[0]
                            if base_mod in OPTIONAL_IMPORTS:
                                imported_module = base_mod
                                break

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            base_mod = node.module.split(".")[0]
                            if base_mod in OPTIONAL_IMPORTS:
                                imported_module = base_mod

                    if imported_module:
                        if node.lineno not in safe_lines:
                            # We found an unprotected import!
                            rel_path = Path(filepath).relative_to(Path.cwd())
                            unprotected_imports.append(
                                f"  - {rel_path}:{node.lineno} (imported '{imported_module}')"
                            )

    error_msg = (
        "\nFound unprotected optional imports! These must be wrapped in a try/except block "
        "to prevent crashing the CLI for users who haven't installed them:\n"
        + "\n".join(unprotected_imports)
    )
    assert not unprotected_imports, error_msg


# Hooks
def test_hook_registry_integrity():
    """Ensure all core hooks can be loaded and have required metadata."""

    HookRegistry.load_builtins()

    hooks = HookRegistry.get_registry()
    assert len(hooks) > 0

    # The standard metadata fields every hook must provide
    required_attrs = ["name", "meta_stage", "meta_category", "meta_desc"]

    for name, _meta in hooks.items():
        hook_cls = HookRegistry.get_class(name)

        assert hook_cls is not None, (
            f"Failed to retrieve class object for hook '{name}'"
        )
        assert hasattr(hook_cls, "run"), f"Hook '{name}' missing 'run' method"

        for attr in required_attrs:
            assert hasattr(hook_cls, attr), (
                f"Hook '{name}' ({hook_cls.__name__}) is missing required attribute: '{attr}'"
            )


def test_hook_stage_mapping():
    class DummyHook(FetchHook):
        meta_stage = "collection"

    # Defaults to the class meta_stage
    hook = DummyHook()
    assert hook.stage == "collection"

    # Can be overridden by the user at runtime
    hook_override = DummyHook(stage="manifest")
    assert hook_override.stage == "manifest"


def test_hook_alias_resolution():
    HookRegistry.load_builtins()

    primary_cls = HookRegistry.get_class("stream-init")
    alias_cls = HookRegistry.get_class("stream_data")

    assert primary_cls is not None
    assert alias_cls is not None
    assert primary_cls is alias_cls


# Registry loading / cache lifecycle
def _make_lifecycle_registry():
    """Create an isolated PluginRegistry for testing load/cache semantics."""

    class LifecycleRegistry(PluginRegistry):
        builtin_pkg = "test.builtins"
        entry_point_group = "test.plugins"
        user_folder = "test"

        calls = {
            "builtins": 0,
            "user": 0,
            "installed": 0,
        }

        @classmethod
        def load_builtins(cls):
            """Mimic PluginRegistry.load_builtins(), including replacement."""
            cls.calls["builtins"] += 1
            registry = cls.get_registry(clear_registry=True)
            registry["builtin"] = {"source": "builtin"}

        @classmethod
        def load_user_plugins(cls):
            cls.calls["user"] += 1
            cls.get_registry()["user"] = {"source": "user"}

        @classmethod
        def load_installed_plugins(cls):
            cls.calls["installed"] += 1
            cls.get_registry()["installed"] = {"source": "installed"}

    return LifecycleRegistry


def test_load_all_populates_complete_registry():
    """The initial load_all() must populate every plugin source."""

    registry_cls = _make_lifecycle_registry()

    registry = registry_cls.load_all()

    assert set(registry) == {"builtin", "user", "installed"}
    assert registry_cls._loaded_registry is registry
    assert registry_cls.calls == {
        "builtins": 1,
        "user": 1,
        "installed": 1,
    }


def test_repeated_load_all_uses_cached_registry():
    """Repeated load_all() calls must not rediscover an unchanged registry."""

    registry_cls = _make_lifecycle_registry()

    first = registry_cls.load_all()
    calls_after_first_load = registry_cls.calls.copy()

    second = registry_cls.load_all()

    assert second is first
    assert registry_cls._loaded_registry is first
    assert registry_cls.calls == calls_after_first_load


def test_registry_replacement_invalidates_loaded_state():
    """Replacing _registry must make the previous loaded marker stale."""

    registry_cls = _make_lifecycle_registry()

    first = registry_cls.load_all()

    replacement = registry_cls.get_registry(clear_registry=True)

    assert replacement is not first
    assert registry_cls._loaded_registry is first

    repaired = registry_cls.load_all()

    assert repaired is registry_cls.get_registry()
    assert repaired is not first
    assert set(repaired) == {"builtin", "user", "installed"}
    assert registry_cls._loaded_registry is repaired


def test_direct_builtin_load_is_repaired_by_load_all():
    """A partial direct load must not leave load_all() permanently cached.

    This reproduces the failure mode where a direct load_builtins() replaces
    a previously complete registry and removes dynamically discovered plugins.
    """

    registry_cls = _make_lifecycle_registry()

    complete = registry_cls.load_all()
    assert set(complete) == {"builtin", "user", "installed"}

    registry_cls.load_builtins()

    partial = registry_cls.get_registry()

    assert partial is not complete
    assert set(partial) == {"builtin"}

    repaired = registry_cls.load_all()

    assert repaired is not partial
    assert set(repaired) == {"builtin", "user", "installed"}
    assert registry_cls._loaded_registry is repaired


def test_dynamic_registration_survives_cached_load_all():
    """Runtime additions must survive when the current registry is complete."""

    registry_cls = _make_lifecycle_registry()

    registry = registry_cls.load_all()
    registry["dynamic"] = {"source": "runtime"}

    calls_before = registry_cls.calls.copy()

    loaded = registry_cls.load_all()

    assert loaded is registry
    assert "dynamic" in loaded
    assert loaded["dynamic"]["source"] == "runtime"
    assert registry_cls.calls == calls_before


def test_reload_all_rebuilds_registry():
    """reload_all() must force discovery and replace the current registry."""

    registry_cls = _make_lifecycle_registry()

    first = registry_cls.load_all()
    first["dynamic"] = {"source": "runtime"}

    calls_before = registry_cls.calls.copy()

    reloaded = registry_cls.reload_all()

    assert reloaded is not first
    assert "dynamic" not in reloaded
    assert set(reloaded) == {"builtin", "user", "installed"}

    assert registry_cls.calls == {
        "builtins": calls_before["builtins"] + 1,
        "user": calls_before["user"] + 1,
        "installed": calls_before["installed"] + 1,
    }

    assert registry_cls._loaded_registry is reloaded


def test_load_all_is_cached_after_reload():
    """A forced reload must establish a new valid fast-path registry."""

    registry_cls = _make_lifecycle_registry()

    registry_cls.load_all()
    reloaded = registry_cls.reload_all()

    calls_after_reload = registry_cls.calls.copy()

    loaded = registry_cls.load_all()

    assert loaded is reloaded
    assert registry_cls.calls == calls_after_reload


def test_loaded_registry_state_is_isolated_per_subclass():
    """One registry being loaded must not mark another registry as loaded."""

    first_cls = _make_lifecycle_registry()
    second_cls = _make_lifecycle_registry()

    first_registry = first_cls.load_all()

    assert first_cls._loaded_registry is first_registry
    assert "_loaded_registry" not in second_cls.__dict__

    second_registry = second_cls.load_all()

    assert second_cls._loaded_registry is second_registry
    assert first_registry is not second_registry

    assert first_cls.calls == {
        "builtins": 1,
        "user": 1,
        "installed": 1,
    }
    assert second_cls.calls == {
        "builtins": 1,
        "user": 1,
        "installed": 1,
    }


def test_load_fast_uses_load_all_cache_semantics():
    """The backwards-compatible load_fast alias should retain the fast path."""

    registry_cls = _make_lifecycle_registry()

    first = registry_cls.load_fast()
    calls_after_first_load = registry_cls.calls.copy()

    second = registry_cls.load_fast()

    assert second is first
    assert registry_cls.calls == calls_after_first_load


def test_yaml_load_all_is_cached():
    loaded = PresetRegistry.load_all()

    assert loaded

    reloaded = PresetRegistry.load_all()

    assert reloaded
    assert loaded is reloaded


def test_yaml_reload_all_reloads():
    loaded = PresetRegistry.load_all()
    reloaded = PresetRegistry.reload_all()

    assert loaded
    assert reloaded
    assert loaded is not reloaded


def test_get_yaml_returns_independent_copy():
    PresetRegistry.load_all()

    first = PresetRegistry.get_yaml("list-only")
    first["hooks"].clear()

    second = PresetRegistry.get_yaml("list-only")
    assert second["hooks"]


def test_hook_mutation():
    HookRegistry.load_all()

    info = HookRegistry.get_info("audit")
    info["desc"] = "mutated"

    assert HookRegistry.get_info("audit")["desc"] != "mutated"
