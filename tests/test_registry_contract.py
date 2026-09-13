# tests/test_registry_contract.py

import sys
import types
import pytest

from fetchez.registry import PluginRegistry, ModuleRegistry


class DummyPlugin:
    name = "dummy"


class DummyRegistry(PluginRegistry):
    base_class = DummyPlugin
    builtin_pkg = "fetchez.test_plugins"
    entry_point_group = "fetchez.test"
    user_folder = "test"


@pytest.fixture(autouse=True)
def clean_registry():
    DummyRegistry._registry = {}
    yield
    DummyRegistry._registry = {}


def make_plugin_module(
    module_name,
    class_name,
    *,
    plugin_name=None,
    aliases=None,
    **metadata,
):
    module = types.ModuleType(module_name)

    attrs = {
        "__module__": module_name,
        "name": plugin_name or class_name.lower(),
    }

    if aliases is not None:
        attrs["meta_aliases"] = aliases

    for key, value in metadata.items():
        attrs[f"meta_{key}"] = value

    plugin_cls = type(
        class_name,
        (DummyPlugin,),
        attrs,
    )

    setattr(module, class_name, plugin_cls)
    sys.modules[module_name] = module

    return module, plugin_cls


def test_registry_extracts_plugin_metadata():
    module, plugin_cls = make_plugin_module(
        "fetchez_test_plugins.example",
        "ExamplePlugin",
        plugin_name="example",
        category="Testing",
        desc="Example plugin",
        tags=["one", "two"],
    )

    DummyRegistry._register_from_module(module)

    meta = DummyRegistry.get_registry()["example"]

    assert meta["category"] == "Testing"
    assert meta["desc"] == "Example plugin"
    assert meta["tags"] == ["one", "two"]

    assert "meta_category" not in meta
    assert meta["_class_obj"] is plugin_cls


def test_registry_supplies_metadata_fallbacks():
    module, _ = make_plugin_module(
        "fetchez_test_plugins.minimal",
        "MinimalPlugin",
        plugin_name="minimal",
    )

    DummyRegistry._register_from_module(module)

    meta = DummyRegistry.get_registry()["minimal"]

    assert meta["category"] == "Generic"
    assert meta["desc"] == "No description provided."
    assert meta["domain"] == "Universal (Files)"
    assert meta["requires"] == "any"


def test_alias_resolves_same_plugin_class():
    module, plugin_cls = make_plugin_module(
        "fetchez_test_plugins.example",
        "ExamplePlugin",
        plugin_name="example",
        aliases=["example-old"],
    )

    DummyRegistry._register_from_module(module)

    assert DummyRegistry.get_class("example") is plugin_cls
    assert DummyRegistry.get_class("example-old") is plugin_cls


def test_unknown_plugin_returns_none():
    assert DummyRegistry.get_class("does-not-exist") is None


def test_external_plugin_cannot_replace_core_plugin():
    core_module, core_cls = make_plugin_module(
        "fetchez.test_plugins.core",
        "CorePlugin",
        plugin_name="shared",
    )

    DummyRegistry._register_from_module(core_module)

    external_module, external_cls = make_plugin_module(
        "external_pkg.plugins",
        "ExternalPlugin",
        plugin_name="shared",
    )

    DummyRegistry._register_from_module(external_module)

    _registry = DummyRegistry.get_registry()

    assert DummyRegistry.get_class("shared") is core_cls
    assert DummyRegistry.get_class("external_pkg.shared") is external_cls


def test_external_alias_keeps_namespaced_identity():
    module, plugin_cls = make_plugin_module(
        "example_ext.hooks",
        "ExternalHook",
        plugin_name="external-hook",
        aliases=["old-hook"],
    )

    DummyRegistry._register_from_module(
        module,
        use_namespaces=True,
    )

    assert DummyRegistry.get_class("example_ext.external-hook") is plugin_cls

    assert DummyRegistry.get_class("example_ext.old-hook") is plugin_cls


def test_registry_ignores_imported_plugin_classes():
    source, imported_cls = make_plugin_module(
        "somewhere_else",
        "ImportedPlugin",
        plugin_name="imported",
    )

    wrapper = types.ModuleType("fetchez_test_plugins.wrapper")
    wrapper.ImportedPlugin = imported_cls

    DummyRegistry._register_from_module(wrapper)

    assert "imported" not in DummyRegistry.get_registry()


def test_registry_does_not_register_base_class():
    module = types.ModuleType("fetchez_test_plugins.base")

    module.DummyPlugin = DummyPlugin

    DummyRegistry._register_from_module(module)

    assert DummyRegistry.get_registry() == {}


def test_registry_ignores_unrelated_classes():
    module = types.ModuleType("fetchez_test_plugins.mixed")

    unrelated = type(
        "Unrelated",
        (),
        {"__module__": module.__name__},
    )
    module.Unrelated = unrelated

    DummyRegistry._register_from_module(module)

    assert DummyRegistry.get_registry() == {}


def test_get_class_resolves_registered_import_path():
    module, plugin_cls = make_plugin_module(
        "fetchez_test_plugins.resolved",
        "ResolvedPlugin",
        plugin_name="resolved",
    )

    DummyRegistry._register_from_module(module)

    assert DummyRegistry.get_class("resolved") is plugin_cls


def test_builtin_registry_reload_is_deterministic():
    ModuleRegistry.load_builtins()

    first = {
        name: meta["import_path"]
        for name, meta in ModuleRegistry.get_registry().items()
    }

    ModuleRegistry.load_builtins()

    second = {
        name: meta["import_path"]
        for name, meta in ModuleRegistry.get_registry().items()
    }

    assert first == second


def test_builtin_module_names_match_registered_classes():
    ModuleRegistry.load_builtins()

    registry = ModuleRegistry.get_registry()

    canonical = {}

    for name, _meta in registry.items():
        plugin_cls = ModuleRegistry.get_class(name)
        assert plugin_cls is not None

        canonical_name = plugin_cls.name

        if canonical_name in canonical:
            assert canonical[canonical_name] is plugin_cls
        else:
            canonical[canonical_name] = plugin_cls
