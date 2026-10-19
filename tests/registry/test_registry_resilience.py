"""Additional offline regression tests for Fetchez registry discovery.

These tests isolate synthetic registry subclasses. Two known limitations are
marked strict xfail, so they become XPASS failures once the bugs are fixed.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import fetchez.registry as registry_module
from fetchez.registry import PluginRegistry, YamlRegistry


class BaseDummy:
    name = "base-dummy"


def make_registry():
    """Each invocation creates a class with independent registry state."""

    class Registry(PluginRegistry):
        base_class = BaseDummy
        builtin_pkg = "fetchez_test_builtins"
        entry_point_group = "fetchez_test_extensions"
        user_folder = "test_extensions"
        _registry = {}
        _loaded_registry = None

    return Registry


def make_plugin(module_name, class_name, name, **attributes):
    module = types.ModuleType(module_name)
    plugin = type(
        class_name,
        (BaseDummy,),
        {"__module__": module_name, "name": name, **attributes},
    )
    setattr(module, class_name, plugin)
    sys.modules[module_name] = module
    return module, plugin


@pytest.fixture
def isolated_registry(monkeypatch):
    cls = make_registry()
    monkeypatch.setattr(registry_module, "get_class_arguments", lambda obj: {})
    return cls


def test_load_all_idempotent_after_registered_plugin(isolated_registry, monkeypatch):
    cls = isolated_registry
    calls = []

    def builtins():
        calls.append("builtin")
        module, _ = make_plugin("fetchez_test_builtins.example", "Example", "example")
        cls._register_from_module(module)

    monkeypatch.setattr(cls, "load_builtins", builtins)
    monkeypatch.setattr(cls, "load_user_plugins", lambda: calls.append("user"))
    monkeypatch.setattr(cls, "load_installed_plugins", lambda: calls.append("external"))

    first = cls.load_all()
    second = cls.load_all()
    assert first is second
    assert calls == ["builtin", "user", "external"]
    assert "example" in second


def test_local_plugin_file_discovery_and_class_lookup(
    isolated_registry, tmp_path, monkeypatch
):
    cls = isolated_registry
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    directory = home / ".fetchez" / cls.user_folder
    directory.mkdir(parents=True)
    cwd.mkdir()
    # Build a standalone base class in an in-memory module and import it from the plugin.
    base_module = types.ModuleType("fetchez_test_dummy_base")
    base_module.BaseDummy = BaseDummy
    monkeypatch.setitem(sys.modules, base_module.__name__, base_module)
    (directory / "custom.py").write_text(
        "from fetchez_test_dummy_base import BaseDummy\n"
        "class Custom(BaseDummy):\n"
        "    name = 'custom'\n"
        "    meta_desc = 'User plugin'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda _: home))
    monkeypatch.chdir(cwd)

    cls.load_user_plugins()
    assert cls.get_class("custom").name == "custom"
    assert cls.get_info("custom")["desc"] == "User plugin"


def test_bad_user_plugin_does_not_hide_good_plugin(
    isolated_registry, tmp_path, monkeypatch, caplog
):
    cls = isolated_registry
    home = tmp_path / "home"
    directory = home / ".fetchez" / cls.user_folder
    directory.mkdir(parents=True)
    (directory / "broken.py").write_text("raise RuntimeError('boom')\n")
    base_module = types.ModuleType("fetchez_test_dummy_base")
    base_module.BaseDummy = BaseDummy
    monkeypatch.setitem(sys.modules, base_module.__name__, base_module)
    (directory / "good.py").write_text(
        "from fetchez_test_dummy_base import BaseDummy\n"
        "class Good(BaseDummy):\n    name = 'good'\n"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda _: home))
    monkeypatch.chdir(tmp_path)

    cls.load_user_plugins()
    assert cls.get_class("good") is not None
    assert "broken.py" in caplog.text


def test_external_package_discovers_nested_python_modules(
    isolated_registry, monkeypatch
):
    cls = isolated_registry
    package = types.ModuleType("fetchez_test_external")
    package.__path__ = ["unused"]
    child, plugin = make_plugin("fetchez_test_external.plugin", "External", "external")
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, child.__name__, child)
    monkeypatch.setattr(
        registry_module.importlib.metadata,
        "entry_points",
        lambda **kwargs: [SimpleNamespace(load=lambda: package)],
    )
    monkeypatch.setattr(
        registry_module.pkgutil,
        "walk_packages",
        lambda **kwargs: [(None, child.__name__, False)],
    )

    cls.load_installed_plugins()
    assert cls.get_class("external") is plugin


def test_external_single_module_entry_point_is_supported(
    isolated_registry, monkeypatch
):
    cls = isolated_registry
    module, plugin = make_plugin("fetchez_test_single_plugin", "Single", "single")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(
        registry_module.importlib.metadata,
        "entry_points",
        lambda **kwargs: [SimpleNamespace(load=lambda: module)],
    )
    cls.load_installed_plugins()
    assert cls.get_class("single") is plugin


def test_external_plugin_failure_does_not_block_other_packages(
    isolated_registry, monkeypatch
):
    cls = isolated_registry
    good = types.ModuleType("fetchez_good_package")
    good.__path__ = ["unused"]
    child, plugin = make_plugin("fetchez_good_package.provider", "Provider", "provider")
    monkeypatch.setitem(sys.modules, good.__name__, good)
    monkeypatch.setitem(sys.modules, child.__name__, child)

    def bad_load():
        raise ImportError("optional dependency unavailable")

    monkeypatch.setattr(
        registry_module.importlib.metadata,
        "entry_points",
        lambda **kwargs: [
            SimpleNamespace(load=bad_load),
            SimpleNamespace(load=lambda: good),
        ],
    )
    monkeypatch.setattr(
        registry_module.pkgutil,
        "walk_packages",
        lambda **kwargs: [(None, child.__name__, False)],
    )
    cls.load_installed_plugins()
    assert cls.get_class("provider") is plugin


def test_user_alias_does_not_replace_builtin_key(isolated_registry):
    cls = isolated_registry

    builtins, builtin = make_plugin("fetchez_test_builtins.core", "Core", "core")
    external, other = make_plugin(
        "outside.plugin", "Other", "other", meta_aliases=["core"]
    )

    cls._register_from_module(builtins)
    cls._register_from_module(external)

    assert cls.get_class("core") is builtin
    assert cls.get_class("outside.core") is other
    assert cls.get_class("other") is other


def test_info_and_list_are_defensive_copies(isolated_registry):
    cls = isolated_registry
    module, _ = make_plugin(
        "fetchez_test_builtins.metadata",
        "Metadata",
        "metadata",
        meta_tags=["original"],
    )
    cls._register_from_module(module)
    info = cls.get_info("metadata")
    all_info = cls.list_all()
    info["tags"].append("changed")
    all_info["metadata"]["tags"].append("changed-again")
    assert cls.get_info("metadata")["tags"] == ["original"]


def test_yaml_registration_skips_invalid_and_empty_documents(tmp_path):
    class Registry(YamlRegistry):
        _registry = {}
        _loaded_registry = None

    Registry._register_yaml("test", "", str(tmp_path / "empty.yaml"))
    Registry._register_yaml("test", "name: [invalid", str(tmp_path / "invalid.yaml"))
    Registry._register_yaml(
        "test", "name: valid\ndescription: Example", str(tmp_path / "ok.yaml")
    )
    assert set(Registry.get_registry()) == {"valid"}
    assert Registry.get_yaml("valid")["provider"] == "test"


def test_yaml_registered_definition_is_not_mutated_by_caller():
    class Registry(YamlRegistry):
        _registry = {}
        _loaded_registry = None

    Registry._register_yaml(
        "test", "name: example\noptions:\n  bands: [1, 2]", "test.yaml"
    )
    first = Registry.get_yaml("example")
    first["options"]["bands"].append(3)
    assert Registry.get_yaml("example")["options"]["bands"] == [1, 2]


def test_yaml_non_mapping_document_reports_clear_validation_error():
    class Registry(YamlRegistry):
        _registry = {}
        _loaded_registry = None

    with pytest.raises(ValueError, match="mapping"):
        Registry._register_yaml("test", "- one\n- two", "list.yaml")


def test_two_external_plugins_with_same_name_dont_clobber(isolated_registry):
    cls = isolated_registry

    builtins, builtin = make_plugin("fetchez_test_builtins.core", "Core", "core")
    external, other = make_plugin(
        "outside.plugin", "Other", "other", meta_aliases=["core"]
    )
    second_external, second_other = make_plugin(
        "second_outside.plugin", "Other", "other", meta_aliases=["core"]
    )

    cls._register_from_module(builtins)
    cls._register_from_module(external)
    cls._register_from_module(second_external)

    assert cls.get_class("core") is builtin
    assert cls.get_class("outside.core") is other
    assert cls.get_class("other") is other
    assert cls.get_class("second_outside.other") is second_other
    assert cls.get_class("second_outside.core") is second_other
