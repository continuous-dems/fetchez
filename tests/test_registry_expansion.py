# tests/test_registry_expansion

from fetchez.registry import PresetRegistry, BundleRegistry
from fetchez.recipe import Recipe


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
