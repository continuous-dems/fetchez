import copy
from fetchez.registry import BundleRegistry


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
                "hooks": [{"name": "audit"}],
            }
        ]
    )
    assert len(expanded) == 3

    hooks = [module.get("hooks", [])[0].get("name") for module in expanded]

    assert hooks == ["audit", "audit", "audit"]
