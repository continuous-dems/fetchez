import copy

import pytest

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
            }
        ]
    )

    expanded_shorthand = BundleRegistry.expand_modules(
        [
            {
                "bundle": "test-bundle",
                "select": {
                    "products": ["1m", "1_9as"],
                },
            }
        ]
    )

    expanded_helper = BundleRegistry.expand_modules(
        [
            {
                "bundle": "test-bundle",
                "select": {
                    "module": "helper",
                },
            }
        ]
    )

    assert len(expanded) == 3
    assert len(expanded_shorthand) == 3
    assert len(expanded_helper) == 1

    products = {
        module.get("args", {}).get("products")
        for module in expanded
        if module.get("module") == "tnm"
    }
    products_shorthand = {
        module.get("args", {}).get("products")
        for module in expanded_shorthand
        if module.get("module") == "tnm"
    }

    assert products == {"1m", "1_9as"}
    assert products_shorthand == {"1m", "1_9as"}

    assert any(module.get("module") == "helper" for module in expanded)
    assert any(module.get("module") == "helper" for module in expanded_shorthand)


def test_bundle_select_combines_fields_with_and(monkeypatch):
    bundle = {
        "name": "test-bundle",
        "modules": [
            {
                "module": "tnm",
                "args": {
                    "products": "1m",
                    "formats": "GeoTIFF",
                },
            },
            {
                "module": "tnm",
                "args": {
                    "products": "1m",
                    "formats": "XYZ",
                },
            },
            {
                "module": "tnm",
                "args": {
                    "products": "1_9as",
                    "formats": "GeoTIFF",
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
                    "args.products": "1m",
                    "args.formats": "GeoTIFF",
                },
            }
        ]
    )

    assert len(expanded) == 1
    assert expanded[0]["args"]["products"] == "1m"
    assert expanded[0]["args"]["formats"] == "GeoTIFF"


def test_bundle_select_rejects_unknown_path(monkeypatch):
    bundle = {
        "name": "test-bundle",
        "modules": [
            {
                "module": "tnm",
                "args": {
                    "products": "1m",
                },
            }
        ],
    }

    monkeypatch.setattr(
        BundleRegistry,
        "get_yaml",
        classmethod(
            lambda cls, name: copy.deepcopy(bundle) if name == "test-bundle" else None
        ),
    )

    with pytest.raises(
        ValueError,
        match="args\\.produts",
    ):
        BundleRegistry.expand_modules(
            [
                {
                    "bundle": "test-bundle",
                    "select": {
                        "args.produts": "1m",
                    },
                }
            ]
        )


def test_preset_select_filters_hooks(monkeypatch):
    preset = {
        "name": "test-preset",
        "hooks": [
            {"name": "checksum", "args": {"algo": "sha256"}},
            {"name": "audit", "args": {"file": "audit.json"}},
            {"name": "enrich"},
        ],
    }

    monkeypatch.setattr(
        PresetRegistry,
        "get_yaml",
        classmethod(
            lambda cls, name: copy.deepcopy(preset) if name == "test-preset" else None
        ),
    )

    expanded = PresetRegistry.expand_hooks(
        [
            {
                "preset": "test-preset",
                "select": {
                    "name": ["checksum", "audit"],
                },
            }
        ]
    )

    assert [hook["name"] for hook in expanded] == [
        "checksum",
        "audit",
    ]
