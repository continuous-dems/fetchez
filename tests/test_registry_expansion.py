# tests/test_registry_expansion

from fetchez.registry import PresetRegistry, BundleRegistry
from fetchez.recipe import Recipe

from copy import deepcopy

from fetchez.registry import (
    ModuleRegistry,
    RecipeRegistry,
)


def test_preset_registry_expansion(monkeypatch):
    """Ensure PresetRegistry properly expands nested presets and overrides args."""

    # Mock a basic preset in the registry for testing
    mock_preset = {
        "name": "test-macro",
        "hooks": [
            {"name": "spatial-crop"},
            {"name": "multi_stack", "args": {"res": "3s", "mode": "mixed"}},
        ],
    }
    monkeypatch.setattr(
        PresetRegistry, "get_yaml", lambda x: mock_preset if x == "test-macro" else None
    )

    # User requests the preset but overrides the resolution
    input_hooks = [
        {"preset": "test-macro", "args": {"multi_stack": {"args": {"res": "1s"}}}}
    ]

    expanded = PresetRegistry.expand_hooks(input_hooks)

    assert len(expanded) == 2
    assert expanded[0]["name"] == "spatial-crop"
    assert expanded[1]["name"] == "multi_stack"
    # Verify the override took effect!
    assert expanded[1]["args"]["res"] == "1s"
    assert expanded[1]["args"]["mode"] == "mixed"


def test_recipe_delegates_to_registry(monkeypatch):
    """Ensure Recipe._expand_hooks delegates directly to PresetRegistry."""

    # Dummy config
    recipe = Recipe({"project": {"name": "test"}})

    input_hooks = [{"name": "audit"}]

    # Spy on PresetRegistry.expand_hooks
    call_tracker = {"called": False}

    def mock_expand(*args, **kwargs):
        call_tracker["called"] = True
        return [{"name": "audit_expanded"}]

    monkeypatch.setattr(PresetRegistry, "expand_hooks", mock_expand)

    result = recipe._expand_hooks(input_hooks)

    assert call_tracker["called"] is True
    assert result[0]["name"] == "audit_expanded"


def test_bundle_registry_expansion(monkeypatch):
    """Ensure BundleRegistry flattens modules and calculates weights."""

    mock_bundle = {
        "name": "coastal-bundle",
        "modules": [
            {"module": "nos_hydro", "args": {"weight": 2.0}},
            {"module": "tnm", "args": {"weight": 1.0}},
        ],
    }
    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        lambda x: mock_bundle if x == "coastal-bundle" else None,
    )

    # User calls the bundle and applies a parent weight multiplier
    input_modules = [{"bundle": "coastal-bundle", "args": {"weight": 0.5}}]

    expanded = BundleRegistry.expand_modules(input_modules)

    assert len(expanded) == 2
    # 2.0 * 0.5 = 1.0
    assert expanded[0]["args"]["weight"] == 1.0
    # 1.0 * 0.5 = 0.5
    assert expanded[1]["args"]["weight"] == 0.5


def test_nested_preset_expansion_loads_registry_once(monkeypatch):
    """Recursive preset expansion must not rediscover YAML at each level."""

    presets = {
        "outer": {
            "hooks": [
                {"preset": "middle"},
            ],
        },
        "middle": {
            "hooks": [
                {"preset": "inner"},
            ],
        },
        "inner": {
            "hooks": [
                {"name": "audit"},
            ],
        },
    }

    calls = {"load": 0}

    def mock_load():
        calls["load"] += 1

    monkeypatch.setattr(PresetRegistry, "load_all", mock_load)
    monkeypatch.setattr(PresetRegistry, "get_yaml", lambda name: presets.get(name))

    expanded = PresetRegistry.expand_hooks([{"preset": "outer"}])

    assert expanded == [{"name": "audit"}]
    assert calls["load"] == 1


def test_private_preset_expansion_never_loads_registry(monkeypatch):
    """_expand_hooks() assumes discovery has already been completed."""

    monkeypatch.setattr(
        PresetRegistry,
        "load_all",
        lambda: (_ for _ in ()).throw(
            AssertionError("_expand_hooks() must not call load_all()")
        ),
    )

    expanded = PresetRegistry._expand_hooks(
        [
            {"name": "audit"},
            {"name": "spatial-crop"},
        ]
    )

    assert expanded == [
        {"name": "audit"},
        {"name": "spatial-crop"},
    ]


def test_private_bundle_expansion_never_loads_registries(monkeypatch):
    """_expand_modules() must be pure recursive expansion."""

    def unexpected_load():
        raise AssertionError("_expand_modules() must not perform registry discovery")

    monkeypatch.setattr(BundleRegistry, "load_all", unexpected_load)
    monkeypatch.setattr(RecipeRegistry, "load_all", unexpected_load)
    monkeypatch.setattr(PresetRegistry, "load_all", unexpected_load)
    monkeypatch.setattr(ModuleRegistry, "load_all", unexpected_load)

    expanded = BundleRegistry._expand_modules(
        [{"module": "tnm", "args": {"weight": 2.0}}]
    )

    assert expanded == [
        {
            "module": "tnm",
            "args": {"weight": 2.0},
        }
    ]


def test_bundle_expansion_loads_dependencies_once(monkeypatch):
    """Nested bundles must not repeatedly load YAML registries."""

    bundles = {
        "outer": {
            "modules": [
                {"bundle": "middle"},
            ],
        },
        "middle": {
            "modules": [
                {"bundle": "inner"},
            ],
        },
        "inner": {
            "modules": [
                {"module": "tnm"},
            ],
        },
    }

    calls = {
        "bundle": 0,
        "recipe": 0,
        "preset": 0,
    }

    def load_bundle():
        calls["bundle"] += 1

    def load_recipe():
        calls["recipe"] += 1

    def load_preset():
        calls["preset"] += 1

    monkeypatch.setattr(BundleRegistry, "load_all", load_bundle)
    monkeypatch.setattr(RecipeRegistry, "load_all", load_recipe)
    monkeypatch.setattr(PresetRegistry, "load_all", load_preset)

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        lambda name: bundles.get(name),
    )

    expanded = BundleRegistry.expand_modules([{"bundle": "outer"}])

    assert expanded == [
        {
            "module": "tnm",
            "args": {"weight": 1.0},
        }
    ]

    assert calls == {
        "bundle": 1,
        "recipe": 1,
        "preset": 1,
    }


def test_nested_bundle_weights_accumulate(monkeypatch):
    """Weights from every bundle level must multiply."""

    bundles = {
        "outer": {
            "modules": [
                {
                    "bundle": "inner",
                    "args": {"weight": 0.5},
                },
            ],
        },
        "inner": {
            "modules": [
                {
                    "module": "tnm",
                    "args": {"weight": 4.0},
                },
            ],
        },
    }

    monkeypatch.setattr(BundleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(RecipeRegistry, "load_all", lambda: None)
    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        lambda name: bundles.get(name),
    )
    monkeypatch.setattr(
        RecipeRegistry,
        "get_yaml",
        lambda name: None,
    )

    expanded = BundleRegistry.expand_modules(
        [
            {
                "bundle": "outer",
                "args": {"weight": 0.25},
            }
        ]
    )

    assert len(expanded) == 1

    # 4.0 * 0.5 * 0.25
    assert expanded[0]["args"]["weight"] == 0.5


def test_bundle_expansion_does_not_mutate_registered_definition(monkeypatch):
    """Expanding a bundle repeatedly must produce identical results."""

    bundle = {
        "name": "weighted",
        "modules": [
            {
                "module": "tnm",
                "args": {"weight": 2.0},
            },
        ],
    }

    original = deepcopy(bundle)

    monkeypatch.setattr(BundleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(RecipeRegistry, "load_all", lambda: None)
    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        lambda name: bundle if name == "weighted" else None,
    )

    request = [
        {
            "bundle": "weighted",
            "args": {"weight": 0.5},
        }
    ]

    first = BundleRegistry.expand_modules(deepcopy(request))
    second = BundleRegistry.expand_modules(deepcopy(request))

    assert first == second
    assert first[0]["args"]["weight"] == 1.0

    # Most importantly, expansion must not modify registry-owned YAML.
    assert bundle == original


def test_preset_expansion_does_not_mutate_registered_definition(monkeypatch):
    preset = {
        "name": "standard",
        "hooks": [
            {
                "name": "multi_stack",
                "args": {
                    "res": "3s",
                    "mode": "mixed",
                },
            }
        ],
    }

    original = deepcopy(preset)

    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)
    monkeypatch.setattr(
        PresetRegistry,
        "get_yaml",
        lambda name: preset if name == "standard" else None,
    )

    request = [
        {
            "preset": "standard",
            "args": {
                "multi_stack": {
                    "args": {"res": "1s"},
                }
            },
        }
    ]

    first = PresetRegistry.expand_hooks(deepcopy(request))
    second = PresetRegistry.expand_hooks(deepcopy(request))

    assert first == second

    assert first == [
        {
            "name": "multi_stack",
            "args": {
                "res": "1s",
                "mode": "mixed",
            },
        }
    ]

    assert preset == original


def test_nested_preset_overrides_propagate_to_leaf(monkeypatch):
    presets = {
        "outer": {
            "hooks": [
                {"preset": "inner"},
            ],
        },
        "inner": {
            "hooks": [
                {
                    "name": "multi_stack",
                    "args": {
                        "res": "3s",
                        "mode": "mixed",
                    },
                }
            ],
        },
    }

    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)
    monkeypatch.setattr(
        PresetRegistry,
        "get_yaml",
        lambda name: presets.get(name),
    )

    expanded = PresetRegistry.expand_hooks(
        [
            {
                "preset": "outer",
                "args": {
                    "multi_stack": {
                        "args": {
                            "res": "1s",
                        }
                    }
                },
            }
        ]
    )

    assert expanded == [
        {
            "name": "multi_stack",
            "args": {
                "res": "1s",
                "mode": "mixed",
            },
        }
    ]


def test_bundle_expansion_can_resolve_recipe(monkeypatch):
    recipe = {
        "config": {
            "modules": [
                {"module": "tnm"},
                {"module": "nos_hydro"},
            ],
        }
    }

    monkeypatch.setattr(BundleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(RecipeRegistry, "load_all", lambda: None)
    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)

    monkeypatch.setattr(BundleRegistry, "get_yaml", lambda name: None)
    monkeypatch.setattr(
        RecipeRegistry,
        "get_yaml",
        lambda name: recipe if name == "test-recipe" else None,
    )

    expanded = BundleRegistry.expand_modules([{"recipe": "test-recipe"}])

    assert [m["module"] for m in expanded] == [
        "tnm",
        "nos_hydro",
    ]


def test_unknown_bundle_name_is_treated_as_module_name(monkeypatch):
    monkeypatch.setattr(BundleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(RecipeRegistry, "load_all", lambda: None)
    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)

    monkeypatch.setattr(BundleRegistry, "get_yaml", lambda name: None)

    expanded = BundleRegistry.expand_modules(["tnm"])

    assert expanded == [{"module": "tnm"}]
