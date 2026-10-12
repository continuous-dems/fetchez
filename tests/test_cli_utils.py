"""Small dependency-free registry helper contract tests (pytest)."""

from fetchez.cli.utils import filter_registry, group_registry_by_key, registry_provider


def test_provider_and_effect_grouping():
    registry = {
        "raster-a": {
            "mod": "globato.hooks.raster",
            "effects": ["filters-chunks", "creates-artifact"],
        },
        "file-b": {"mod": "fetchez.hooks.files", "effects": ["creates-artifact"]},
        "local-c": {"mod": "fetchez_user.hooks.local"},
    }
    assert registry_provider(registry["file-b"]) == "builtin"
    assert registry_provider(registry["local-c"]) == "user"
    assert set(filter_registry(registry, {"provider": "globato"})) == {"raster-a"}
    assert set(filter_registry(registry, {"effects": "creates-artifact"})) == {
        "raster-a",
        "file-b",
    }
    assert set(
        filter_registry(
            registry,
            {"provider": ["globato", "builtin"], "effects": "creates-artifact"},
        )
    ) == {"raster-a", "file-b"}
    grouped = group_registry_by_key(registry, "effects")
    assert {name for name, _ in grouped["creates-artifact"]} == {"raster-a", "file-b"}
    assert {name for name, _ in grouped["Unspecified"]} == {"local-c"}


def test_metadata_prefix_and_alias():
    registry = {
        "foo": {"meta_effects": ["modifies-entries"], "aliases": ["alias"]},
        "alias": {"meta_effects": ["modifies-entries"], "aliases": ["alias"]},
    }
    assert set(filter_registry(registry, {"effects": "MODIFIES-ENTRIES"})) == {
        "foo",
        "alias",
    }
    assert [
        name
        for name, _ in group_registry_by_key(registry, "effects")["modifies-entries"]
    ] == ["foo"]
