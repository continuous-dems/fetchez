# test_recipe.py

import json
from pathlib import Path
import pytest
from unittest.mock import patch
from fetchez.recipe import Recipe


def test_recipe_initialization():
    """Ensure a Recipe initializes correctly from a raw dictionary."""

    config = {"project": {"name": "Test Project", "description": "A test recipe"}}
    recipe = Recipe(config)

    assert recipe.name == "Test Project"
    assert recipe.config["project"]["description"] == "A test recipe"

    with pytest.raises(FileNotFoundError):
        recipe = Recipe("/tmp/test.yaml")

    with pytest.raises(FileNotFoundError):
        recipe = Recipe.from_file("/tmp/test.yaml")

    assert Recipe.from_file == Recipe.from_dict


def test_get_module_signature():
    """Verify that module signatures correctly differentiate datasets to prevent aggressive deduplication."""

    recipe = Recipe({})

    # Simple strings and basic dicts should fall back to just the module name
    assert recipe._get_module_signature("tnm") == "tnm"
    assert recipe._get_module_signature({"module": "tnm"}) == "tnm"

    # Modules with distinguishing arguments should generate unique signatures
    mod_ned1 = {"module": "tnm", "args": {"datasets": "1", "weight": 1.0}}
    mod_ned3 = {"module": "tnm", "args": {"datasets": "3", "weight": 1.0}}

    sig_1 = recipe._get_module_signature(mod_ned1)
    sig_3 = recipe._get_module_signature(mod_ned3)

    assert sig_1 == "tnm::datasets=1"
    assert sig_3 == "tnm::datasets=3"
    assert sig_1 != sig_3


@patch("fetchez.registry.BundleRegistry.get_yaml")
def test_expand_modules_recursive_and_deduplucate(mock_get_bundle):
    """Test that bundles expand recursively and parent definitions override child arguments."""

    # Mock a base bundle that provides 'ehydro' at weight 1.0 with an unzip hook
    mock_get_bundle.return_value = {
        "modules": [
            {"module": "ehydro", "args": {"weight": 1.0}, "hooks": [{"name": "unzip"}]}
        ]
    }

    recipe = Recipe({})

    # The parent pipeline: Import the bundle, then override 'ehydro' weight
    raw_modules = [
        {"bundle": "mock_base_bundle"},
        {"module": "ehydro", "args": {"weight": 5.0}},
    ]

    expanded = recipe._expand_modules(raw_modules)

    # These should merge into 2 modules
    assert len(expanded) == 2

    final_mod = expanded[0]
    assert final_mod["module"] == "ehydro"
    assert final_mod["args"]["weight"] == 1.0
    assert final_mod["hooks"][0]["name"] == "unzip"

    final_mod = expanded[1]
    assert final_mod["module"] == "ehydro"
    assert final_mod["args"]["weight"] == 5.0
    assert final_mod.get("hooks") is None


def test_to_cli_translation():
    """Verify the Recipe configuration correctly translates into a Fetchez CLI string."""

    config = {
        "region": "-120.0/-119.0/33.0/34.0",
        "region_srs": "EPSG:4326",
        "execution": {"threads": 4},
        "global_hooks": [{"name": "audit", "args": {"file": "log.json"}}],
        "modules": [
            {"module": "copernicus", "args": {"datatype": 3}},
            {
                "bundle": "crm_standard",
                "args": {"weight": 2.0},
                "hooks": [{"name": "pipe"}],
            },
        ],
    }
    recipe = Recipe(config)
    cli_str = recipe.to_cli()

    # Check base arguments
    assert "fetchez build" in cli_str
    assert "-R -120.0/-119.0/33.0/34.0" in cli_str
    assert "--region-srs EPSG:4326" in cli_str
    assert "--threads 4" in cli_str

    # Check global hooks
    assert "--global-hook audit:file=log.json" in cli_str

    # Check modules and their specific args/hooks
    assert "copernicus --datatype 3" in cli_str
    assert "crm_standard --weight 2.0" in cli_str
    assert "--hook pipe" in cli_str


def test_to_json_translation():
    """Verify the Recipe serializes cleanly to JSON."""

    config = {"project": {"name": "JSON Test"}, "modules": ["tnm"]}
    recipe = Recipe(config)

    json_str = recipe.to_json()
    parsed = json.loads(json_str)

    assert parsed["project"]["name"] == "JSON Test"
    assert parsed["modules"][0] == "tnm"


def test_recipe_utils():
    resolved_path = Recipe({})._resolve_path("./test")
    assert Path(resolved_path) == Path.cwd() / "test"
