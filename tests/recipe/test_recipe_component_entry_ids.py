"""Offline contracts for module/hook occurrence IDs in Recipe.

These tests complement test_recipe_entry_ids.py and
 test_recipe_instance_context_contracts.py; no fetch or pipeline execution is needed.
"""

import pytest

from fetchez.hooks import FetchHook
from fetchez.modules.base import FetchModule
from fetchez.recipe import Recipe, _component_entry_ids


class NamedModule(FetchModule):
    name = "component-id-test-module"

    def __init__(self, **kwargs):
        super().__init__(use_cache=False, **kwargs)

    def run(self):
        return self


class NamedHook(FetchHook):
    name = "component-id-test-hook"

    def run(self, entries):
        return entries


@pytest.mark.parametrize(
    ("base_class", "key", "prefix", "expected"),
    [
        (FetchModule, "module", "entry", ["entry_1_2", "entry_1", "entry_3"]),
        (FetchHook, "name", "hook", ["hook_1_2", "hook_1", "hook_3"]),
    ],
)
def test_component_entry_ids_reserve_explicit_labels_before_generating(
    base_class, key, prefix, expected
):
    definitions = [
        {key: NamedModule if key == "module" else NamedHook},
        {key: NamedModule if key == "module" else NamedHook, "id": f"{prefix}_1"},
        {key: NamedModule if key == "module" else NamedHook},
    ]
    assert (
        _component_entry_ids(definitions, base_class=base_class, key=key, prefix=prefix)
        == expected
    )
    assert definitions[0].get("id") is None  # No mutation of the input declarations.


@pytest.mark.parametrize(
    ("base_class", "key", "prefix", "component"),
    [
        (FetchModule, "module", "entry", NamedModule),
        (FetchHook, "name", "hook", NamedHook),
    ],
)
@pytest.mark.parametrize("invalid", ["", " padded ", 0, None])
def test_component_entry_ids_reject_invalid_explicit_values(
    base_class, key, prefix, component, invalid
):
    with pytest.raises(ValueError, match="instance id"):
        _component_entry_ids(
            [{key: component, "id": invalid}],
            base_class=base_class,
            key=key,
            prefix=prefix,
        )


@pytest.mark.parametrize(
    ("base_class", "key", "prefix", "component"),
    [
        (FetchModule, "module", "entry", NamedModule),
        (FetchHook, "name", "hook", NamedHook),
    ],
)
def test_component_entry_ids_reject_duplicate_explicit_values(
    base_class, key, prefix, component
):
    with pytest.raises(ValueError, match="Duplicate .* instance id"):
        _component_entry_ids(
            [{key: component, "id": "shared"}, {key: component, "id": "shared"}],
            base_class=base_class,
            key=key,
            prefix=prefix,
        )


def test_hook_ids_are_metadata_and_visible_in_compiled_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    recipe = Recipe(
        {
            "global_hooks": [
                {"name": NamedHook, "id": "first"},
                {"name": NamedHook, "id": "second"},
                {"name": NamedHook},
            ],
            "modules": [],
        }
    )

    plan = recipe.compile()
    assert [hook.instance_id for hook in plan.global_hooks] == [
        "first",
        "second",
        "hook_3",
    ]
    assert [hook.instance_id_explicit for hook in plan.global_hooks] == [
        True,
        True,
        False,
    ]
    assert len({id(hook) for hook in plan.global_hooks}) == 3
    assert plan.global_hooks_by_id == dict(
        zip(["first", "second", "hook_3"], plan.global_hooks, strict=True)
    )
    assert recipe.config["global_hooks"][0]["id"] == "first"
    assert "instance_id" not in recipe.config["global_hooks"][2]


def test_hooks_with_same_name_can_have_distinct_ids():
    hooks = Recipe({"modules": []})._init_hooks(
        [
            {"name": NamedHook, "id": "primary"},
            {"name": NamedHook, "id": "secondary"},
        ]
    )
    assert hooks[0].name == hooks[1].name
    assert hooks[0] is not hooks[1]
    assert [hook.instance_id for hook in hooks] == ["primary", "secondary"]


def test_duplicate_hook_ids_fail_during_compilation():
    recipe = Recipe(
        {
            "modules": [],
            "global_hooks": [
                {"name": NamedHook, "id": "shared"},
                {"name": NamedHook, "id": "shared"},
            ],
        }
    )
    with pytest.raises(ValueError, match="Duplicate .* instance id"):
        recipe.compile()


def test_hook_ids_are_scoped_to_each_hook_collection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = Recipe(
        {
            "global_hooks": [{"name": NamedHook, "id": "qc"}],
            "modules": [
                {
                    "module": NamedModule,
                    "id": "one",
                    "hooks": [{"name": NamedHook, "id": "qc"}],
                },
                {
                    "module": NamedModule,
                    "id": "two",
                    "hooks": [{"name": NamedHook, "id": "qc"}],
                },
            ],
        }
    ).compile()
    assert plan.global_hooks_by_id["qc"] is plan.global_hooks[0]
    assert plan.modules_by_id.keys() == {"one", "two"}
    assert [module.hooks[0].instance_id for module in plan.modules] == ["qc", "qc"]
    assert plan.modules[0].hooks[0] is not plan.modules[1].hooks[0]


def test_duplicate_ids_in_one_module_local_hook_list_fail():
    recipe = Recipe(
        {
            "modules": [
                {
                    "module": NamedModule,
                    "hooks": [
                        {"name": NamedHook, "id": "dup"},
                        {"name": NamedHook, "id": "dup"},
                    ],
                },
            ]
        }
    )
    with pytest.raises(ValueError, match="Duplicate .* instance id"):
        recipe.compile()


def test_duplicate_python_hook_object_is_rejected():
    hook = NamedHook()
    with pytest.raises(ValueError, match="same hook object"):
        Recipe({"modules": []})._init_hooks(
            [
                {"name": hook, "id": "one"},
                {"name": hook, "id": "two"},
            ]
        )


def test_python_hook_instance_identity_and_explicit_wrapper_override():
    hook = NamedHook()
    hook.instance_id = "from_python"
    hook.instance_id_explicit = True
    plan = Recipe({"modules": [], "global_hooks": [hook]}).compile()
    assert plan.global_hooks_by_id["from_python"] is hook

    plan = Recipe(
        {
            "modules": [],
            "global_hooks": [
                {"name": hook, "id": "from_yaml"},
            ],
        }
    ).compile()
    assert plan.global_hooks_by_id["from_yaml"] is hook
    assert hook.instance_id_explicit is True


def test_generated_hook_label_stays_implicit_across_compiles():
    hook = NamedHook()
    recipe = Recipe({"modules": [], "global_hooks": [hook]})
    first = recipe.compile()
    assert first.global_hooks[0] is hook
    assert hook.instance_id == "hook_1"
    assert hook.instance_id_explicit is False

    second = recipe.compile()
    assert second.global_hooks[0] is hook
    assert hook.instance_id == "hook_1"
    assert hook.instance_id_explicit is False


def test_module_and_hook_ids_use_separate_namespaces():
    plan = Recipe(
        {
            "modules": [{"module": NamedModule, "id": "shared"}],
            "global_hooks": [{"name": NamedHook, "id": "shared"}],
        }
    ).compile()
    assert plan.modules_by_id["shared"] is plan.modules[0]
    assert plan.global_hooks_by_id["shared"] is plan.global_hooks[0]


def test_hook_ids_are_checked_after_recipe_modifiers(monkeypatch):
    recipe = Recipe(
        {
            "modules": [],
            "global_hooks": [{"name": NamedHook, "id": "primary"}],
        }
    )

    class DuplicateHookModifier:
        def apply(self, config):
            config["global_hooks"].append({"name": NamedHook, "id": "primary"})
            return config

    monkeypatch.setattr(
        recipe, "_init_modifiers", lambda *a, **kw: [DuplicateHookModifier()]
    )
    with pytest.raises(ValueError, match="Duplicate .* instance id"):
        recipe.compile()
