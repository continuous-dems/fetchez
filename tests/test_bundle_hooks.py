import copy

import pytest
from click.testing import CliRunner

from fetchez.cli.pipeline import make_bundle_command
from fetchez.registry import BundleRegistry, PresetRegistry


def test_bundle_select_filters_matching_members_and_keeps_unkeyed(monkeypatch):
    bundle = {
        "name": "test-bundle",
        "modules": [
            {
                "module": "tnm",
                "args": {
                    "products": "1m",
                    "weight": 1.0,
                },
            },
            {
                "module": "tnm",
                "args": {
                    "products": "1_9as",
                    "weight": 0.5,
                },
            },
            {
                "module": "tnm",
                "args": {
                    "products": "1_3as",
                    "weight": 0.25,
                },
            },
            {
                "module": "helper",
                "args": {
                    "enabled": True,
                },
            },
        ],
    }

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        classmethod(
            lambda cls, name: copy.deepcopy(bundle) if name == "test-bundle" else None
        ),
    )

    expanded = BundleRegistry.expand_modules(
        [
            {
                "bundle": "test-bundle",
                "select": {
                    "args.products": ["1m", "1_9as"],
                },
                "append_hooks": [{"name": "audit"}],
            }
        ]
    )
    assert len(expanded) == 3

    hooks = [module.get("hooks", [])[0].get("name") for module in expanded]

    assert hooks == ["audit", "audit", "audit"]


@pytest.fixture
def bundle_defs(monkeypatch):
    """Provide an isolated in-memory bundle registry."""

    bundles = {}

    def get_yaml(cls, name):
        value = bundles.get(name)
        return copy.deepcopy(value) if value is not None else None

    # Avoid discovering real presets/plugins during these unit tests.
    monkeypatch.setattr(
        PresetRegistry,
        "load_all",
        classmethod(lambda cls: {}),
    )

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        classmethod(get_yaml),
    )

    # Keep identity/deduplication deterministic without requiring real modules.
    monkeypatch.setattr(
        BundleRegistry,
        "get_module_signature",
        staticmethod(
            lambda mod: (
                mod
                if isinstance(mod, str)
                else f"{mod.get('module')}:{mod.get('args', {}).get('variant', '')}"
            )
        ),
    )

    return bundles


def _by_name(modules):
    return {module["module"]: module for module in modules}


def _hook(module, name):
    for hook in module.get("hooks", []):
        if hook.get("name") == name:
            return hook
    return None


def test_bundle_hook_override_updates_existing_hook_only(bundle_defs):
    """Bundle `hooks` are sparse overrides and must not create new hooks."""

    bundle_defs["base"] = {
        "modules": [
            {
                "module": "has-mask",
                "hooks": [
                    {
                        "name": "point_raster_mask",
                        "args": {
                            "barrier": "land",
                            "res": "3s",
                        },
                    }
                ],
            },
            {
                "module": "no-mask",
                "hooks": [
                    {
                        "name": "raster_warp",
                        "args": {"res": "3s"},
                    }
                ],
            },
        ]
    }

    expanded = BundleRegistry._expand_modules(
        [
            {
                "bundle": "base",
                "hooks": [
                    {
                        "name": "point_raster_mask",
                        "args": {"res": "1s"},
                    }
                ],
            }
        ]
    )

    modules = _by_name(expanded)

    mask = _hook(modules["has-mask"], "point_raster_mask")
    assert mask is not None
    assert mask["args"] == {
        "barrier": "land",
        "res": "1s",
    }

    # Critical regression check:
    # an override must not create point_raster_mask where it was absent.
    assert _hook(modules["no-mask"], "point_raster_mask") is None

    warp = _hook(modules["no-mask"], "raster_warp")
    assert warp["args"]["res"] == "3s"


def test_bundle_append_hooks_add_missing_hook_to_children(bundle_defs):
    """Explicit `append_hooks` add a hook when it does not already exist."""

    bundle_defs["base"] = {
        "modules": [
            {"module": "one"},
            {
                "module": "two",
                "hooks": [
                    {
                        "name": "raster_warp",
                        "args": {"res": "3s"},
                    }
                ],
            },
        ]
    }

    expanded = BundleRegistry._expand_modules(
        [
            {
                "bundle": "base",
                "append_hooks": [
                    {
                        "name": "audit",
                        "args": {"stage": "manifest"},
                    }
                ],
            }
        ]
    )

    modules = _by_name(expanded)

    for name in ("one", "two"):
        audit = _hook(modules[name], "audit")
        assert audit is not None
        assert audit["args"] == {"stage": "manifest"}

    # Existing unrelated hooks remain intact.
    assert _hook(modules["two"], "raster_warp")["args"] == {"res": "3s"}


def test_bundle_append_hook_overrides_same_name_hook(bundle_defs):
    """Appending an already-present hook updates it instead of duplicating it."""

    bundle_defs["base"] = {
        "modules": [
            {
                "module": "one",
                "hooks": [
                    {
                        "name": "audit",
                        "args": {
                            "stage": "manifest",
                            "output": "original.json",
                        },
                    }
                ],
            }
        ]
    }

    expanded = BundleRegistry._expand_modules(
        [
            {
                "bundle": "base",
                "append_hooks": [
                    {
                        "name": "audit",
                        "args": {"output": "custom.json"},
                    }
                ],
            }
        ]
    )

    module = expanded[0]

    audit_hooks = [
        hook for hook in module.get("hooks", []) if hook.get("name") == "audit"
    ]

    assert len(audit_hooks) == 1
    assert audit_hooks[0]["args"] == {
        "stage": "manifest",
        "output": "custom.json",
    }


def test_nested_bundle_hook_overrides_do_not_create_missing_hooks(bundle_defs):
    """Overrides on an inherited bundle propagate only to matching child hooks."""

    bundle_defs["global-bathy-topo"] = {
        "modules": [
            {
                "module": "masked-source",
                "hooks": [
                    {
                        "name": "point_raster_mask",
                        "args": {
                            "barrier": "land",
                            "res": "3s",
                        },
                    }
                ],
            },
            {
                "module": "plain-source",
                "hooks": [
                    {
                        "name": "raster_warp",
                        "args": {"res": "3s"},
                    }
                ],
            },
        ]
    }

    bundle_defs["crm-standard"] = {
        "modules": [
            {
                "bundle": "global-bathy-topo",
                "hooks": [
                    {
                        "name": "point_raster_mask",
                        "args": {"res": "1s"},
                    }
                ],
            }
        ]
    }

    expanded = BundleRegistry._expand_modules([{"bundle": "crm-standard"}])

    modules = _by_name(expanded)

    mask = _hook(modules["masked-source"], "point_raster_mask")
    assert mask["args"] == {
        "barrier": "land",
        "res": "1s",
    }

    # This is the exact regression that caused the barrier errors.
    assert _hook(modules["plain-source"], "point_raster_mask") is None


def test_nested_bundle_append_hooks_explicitly_add_missing_hooks(bundle_defs):
    """`append_hooks` remains intentionally additive through bundle expansion."""

    bundle_defs["inner"] = {
        "modules": [
            {"module": "one"},
            {"module": "two"},
        ]
    }

    bundle_defs["outer"] = {
        "modules": [
            {
                "bundle": "inner",
                "append_hooks": [
                    {"name": "audit"},
                ],
            }
        ]
    }

    expanded = BundleRegistry._expand_modules([{"bundle": "outer"}])

    modules = _by_name(expanded)

    assert _hook(modules["one"], "audit") is not None
    assert _hook(modules["two"], "audit") is not None


def test_bundle_cli_hook_becomes_append_hook():
    command = make_bundle_command(
        "test-bundle",
        {"description": "Test bundle"},
    )

    result = CliRunner().invoke(
        command,
        ["--hook", "audit:stage=manifest"],
        standalone_mode=False,
    )

    assert result.exception is None

    config = result.return_value

    assert "hooks" not in config
    assert config["append_hooks"] == [
        {
            "name": "audit",
            "args": {"stage": "manifest"},
        }
    ]
