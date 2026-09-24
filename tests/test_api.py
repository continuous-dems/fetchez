# tests/test_api.py

import pytest

import fetchez
from fetchez import api


def test_api_import():
    assert callable(fetchez.get)
    assert callable(fetchez.run_recipe)


def test_api_modules():
    modules = fetchez.list_modules()
    module_keys = modules.keys()
    assert "charts" in module_keys
    assert "osm" in module_keys

    # Make sure all mods have a 'cli_args'
    for mod in module_keys:
        assert modules[mod].get("cli_args")

    for mod in module_keys:
        assert modules[mod].get("category")

    mbdb_results = fetchez.search_modules("mbdb")
    assert len(mbdb_results) >= 1
    assert isinstance(mbdb_results, dict)
    assert mbdb_results.get("mbdb")


class DummyRegistry:
    _registry = {
        "alpha": {
            "desc": "Coastal bathymetry provider",
            "tags": ["ocean", "elevation"],
            "aliases": ["a", "first"],
            "category": "Bathymetry",
            "nested": {"value": 1},
        },
        "beta": {
            "desc": "Generic topography source",
            "tags": ["land"],
            "aliases": ["b"],
            "category": "Topography",
        },
    }
    load_count = 0

    @classmethod
    def load_all(cls):
        cls.load_count += 1
        return cls._registry

    @classmethod
    def get_registry(cls):
        return cls._registry


@pytest.fixture(autouse=True)
def reset_dummy_registry():
    DummyRegistry.load_count = 0
    DummyRegistry._registry["alpha"]["nested"]["value"] = 1


def test_search_registry_loads_registry():
    result = api._search_registry(DummyRegistry)

    assert DummyRegistry.load_count == 1
    assert set(result) == {"alpha", "beta"}


def test_search_registry_without_term_returns_copy():
    result = api._search_registry(DummyRegistry)

    result["alpha"]["nested"]["value"] = 999
    result["alpha"]["tags"].append("mutated")

    assert DummyRegistry._registry["alpha"]["nested"]["value"] == 1
    assert "mutated" not in DummyRegistry._registry["alpha"]["tags"]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("alpha", {"alpha"}),  # name
        ("coast", {"alpha"}),  # description
        ("elev", {"alpha"}),  # tag substring
        ("fir", {"alpha"}),  # alias substring
        ("bathy", {"alpha"}),  # category substring
        ("topo", {"beta"}),  # category substring
    ],
)
def test_search_registry_matches_metadata(term, expected):
    result = api._search_registry(DummyRegistry, term)
    assert set(result) == expected


def test_search_registry_is_case_insensitive():
    lower = api._search_registry(DummyRegistry, "coastal")
    upper = api._search_registry(DummyRegistry, "COASTAL")

    assert lower == upper


def test_search_registry_returns_empty_dict_for_no_match():
    assert api._search_registry(DummyRegistry, "does-not-exist") == {}


def test_search_registry_results_are_independent():
    result = api._search_registry(DummyRegistry, "alpha")
    result["alpha"]["nested"]["value"] = 999

    second = api._search_registry(DummyRegistry, "alpha")

    assert second["alpha"]["nested"]["value"] == 1


@pytest.mark.parametrize(
    ("func", "registry"),
    [
        (api.list_modules, api.ModuleRegistry),
        (api.list_bundles, api.BundleRegistry),
        (api.list_hooks, api.HookRegistry),
        (api.list_recipes, api.RecipeRegistry),
        (api.list_schemas, api.SchemaRegistry),
        (api.list_modifiers, api.ModifierRegistry),
        (api.list_presets, api.PresetRegistry),
        (api.list_streams, api.StreamRegistry),
        (api.list_readers, api.ReaderRegistry),
        (api.list_profiles, api.ProfileRegistry),
    ],
)
def test_list_helpers_use_correct_registry(monkeypatch, func, registry):
    seen = {}

    def fake_search(registry_cls, term=None):
        seen["registry"] = registry_cls
        seen["term"] = term
        return {"ok": {}}

    monkeypatch.setattr(api, "_search_registry", fake_search)

    assert func() == {"ok": {}}
    assert seen == {"registry": registry, "term": None}


@pytest.mark.parametrize(
    ("func", "registry"),
    [
        (api.search_modules, api.ModuleRegistry),
        (api.search_bundles, api.BundleRegistry),
        (api.search_hooks, api.HookRegistry),
        (api.search_recipes, api.RecipeRegistry),
        (api.search_schemas, api.SchemaRegistry),
        (api.search_modifiers, api.ModifierRegistry),
        (api.search_presets, api.PresetRegistry),
        (api.search_streams, api.StreamRegistry),
        (api.search_readers, api.ReaderRegistry),
        (api.search_profiles, api.ProfileRegistry),
    ],
)
def test_search_helpers_use_correct_registry(monkeypatch, func, registry):
    seen = {}

    def fake_search(registry_cls, term=None):
        seen["registry"] = registry_cls
        seen["term"] = term
        return {"match": {}}

    monkeypatch.setattr(api, "_search_registry", fake_search)

    assert func("needle") == {"match": {}}
    assert seen == {"registry": registry, "term": "needle"}


def test_search_queries_all_registries(monkeypatch):
    calls = []

    def fake_search(registry_cls, term=None):
        calls.append((registry_cls, term))
        return {"result": {}}

    monkeypatch.setattr(api, "_search_registry", fake_search)

    result = api.search("coastal")

    assert set(result) == {
        "modules",
        "bundles",
        "hooks",
        "recipes",
        "schemas",
        "modifiers",
        "presets",
        "streams",
        "readers",
        "profiles",
    }

    assert len(calls) == 10
    assert all(term == "coastal" for _, term in calls)


def test_search_registry_tags_support_substring_matching():
    result = api._search_registry(DummyRegistry, "elev")

    assert "alpha" in result


def test_search_registry_aliases_support_substring_matching():
    result = api._search_registry(DummyRegistry, "fir")

    assert "alpha" in result
