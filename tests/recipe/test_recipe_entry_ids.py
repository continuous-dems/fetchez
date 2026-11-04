"""Recipe labels distinguish declarations without changing provider cache IDs."""

import pytest
from fetchez.modules.base import FetchModule
from fetchez.recipe import Recipe, PipelinePlan


class EntryFixture(FetchModule):
    name = "recipe-entry-fixture"

    def run(self):
        return self


def test_entry_ids_preserve_separate_owners_and_provider_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    recipe = Recipe({"modules": []})
    mods = recipe._init_modules(
        [
            {"module": EntryFixture, "id": "target"},
            {"module": EntryFixture, "id": "reference"},
        ]
    )

    plan = PipelinePlan(
        config={},
        modules=mods,
        global_hooks=[],
    )

    assert plan.modules_by_id == {
        "target": mods[0],
        "reference": mods[1],
    }
    assert mods[0] is not mods[1]
    assert mods[0].module_id() == mods[1].module_id()

    # assert [m.instance_id for m in mods] == ["target", "reference"]
    # assert mods[0]._instance_ids == frozenset(["target", "reference"])
    defaults = recipe._init_modules(
        [{"module": EntryFixture}, {"module": EntryFixture}]
    )
    assert [m.instance_id for m in defaults] == ["entry_1", "entry_2"]


@pytest.mark.parametrize("identities", [["same", "same"], [""], [" padded "], [1]])
def test_invalid_entry_ids_fail(tmp_path, monkeypatch, identities):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        Recipe({"modules": []})._init_modules(
            [{"module": EntryFixture, "id": value} for value in identities]
        )


def test_duplicate_yaml_ids_fail_before_bundle_deduplication():
    definition = {"module": "scratch", "id": "same"}
    with pytest.raises(ValueError, match="Duplicate module instance id"):
        Recipe({"modules": [definition, definition]}).compile()


def test_normal_compilation_retains_identical_provider_definitions_with_distinct_ids(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    plan = Recipe(
        {
            "modules": [
                {"module": "scratch", "id": "target"},
                {"module": "scratch", "id": "reference"},
            ]
        }
    ).compile()
    assert [m.instance_id for m in plan.modules] == ["target", "reference"]
    assert plan.modules[0].module_id() == plan.modules[1].module_id()


def test_automatic_display_labels_do_not_conflict_with_explicit_ids():
    modules = Recipe({"modules": []})._init_modules(
        [{"module": EntryFixture}, {"module": EntryFixture, "id": "entry_1"}]
    )
    assert [m.instance_id for m in modules] == ["entry_1_2", "entry_1"]
    assert [m.instance_id_explicit for m in modules] == [False, True]


def test_id_is_metadata_not_a_provider_option_and_preserves_original_config():
    definition = {"module": EntryFixture, "id": "readable"}
    recipe = Recipe({"modules": [definition]})
    first = recipe.compile().modules[0]
    second = recipe.compile().modules[0]
    assert first is not second
    assert first.instance_id == second.instance_id == "readable"
    assert "id" not in first._init_kwargs
    unnamed = Recipe({"modules": [{"module": EntryFixture}]}).compile().modules[0]
    assert first.module_id() == unnamed.module_id()
    assert recipe.config["modules"] == [definition]


def test_same_runtime_object_cannot_have_two_recipe_owners():
    instance = EntryFixture()
    with pytest.raises(ValueError, match="same module object"):
        Recipe({"modules": []})._init_modules(
            [{"module": instance, "id": "one"}, {"module": instance, "id": "two"}]
        )


def test_prepared_ids_are_checked_after_modifiers(monkeypatch):
    recipe = Recipe({"modules": [{"module": "scratch", "id": "one"}]})

    class Duplicate:
        def apply(self, config):
            config["modules"].append({"module": "scratch", "id": "one"})
            return config

    monkeypatch.setattr(recipe, "_init_modifiers", lambda *a, **kw: [Duplicate()])
    with pytest.raises(ValueError, match="Duplicate module instance id"):
        recipe.compile()
