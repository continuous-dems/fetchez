"""Offline tests for the generic ensure-hook recipe modifier."""

import pytest

from fetchez.recipes.modifiers.ensure_hook import EnsureHook


@pytest.fixture
def modifier_cls(monkeypatch):
    return EnsureHook


def test_stack_qc_inserted_once_from_local_opt_in(modifier_cls):
    cfg = {
        "modules": [
            {
                "module": "local",
                "hooks": [
                    {"name": "stack-qc", "args": {"viz": True}},
                    {"name": "stack-qc", "args": {"viz": False}},
                ],
            }
        ]
    }
    modifier = modifier_cls(
        when={"hook": "stack-qc", "args": {"viz": True}},
        ensure={"name": "raster-viz", "scope": "global"},
    )
    assert modifier.apply(cfg)["global_hooks"] == [{"name": "raster-viz"}]
    modifier.apply(cfg)
    assert len(cfg["global_hooks"]) == 1


def test_spatial_claim_defaults_and_prepend(modifier_cls):
    cfg = {
        "modules": [
            {
                "module": "local",
                "hooks": [
                    {"name": "claim_grid_filter", "args": {}},
                    {"name": "claim-grid-filter", "args": {"res": "2s"}},
                ],
            }
        ],
        "global_hooks": [{"name": "audit"}],
    }
    mod = modifier_cls(
        when={"hook": "claim-grid-filter"},
        ensure={"name": "spatial-claim", "position": "prepend"},
        set_defaults={"res": "1s"},
    )
    mod.apply(cfg)
    assert cfg["modules"][0]["hooks"][0]["args"]["res"] == "1s"
    assert cfg["modules"][0]["hooks"][1]["args"]["res"] == "2s"
    assert cfg["global_hooks"] == [{"name": "spatial-claim"}, {"name": "audit"}]
    mod.apply(cfg)
    assert len(cfg["global_hooks"]) == 2


def test_scoped_forwarding_preserves_distinct_reports(modifier_cls):
    cfg = {
        "global_hooks": [
            {"name": "stack-qc", "args": {"viz": True, "group_by": "module"}},
            {"name": "stack-qc", "args": {"viz": True, "group_by": "source"}},
        ]
    }
    mod = modifier_cls(
        when={"hook": "stack-qc", "args": {"viz": True}},
        ensure={"name": "raster-viz"},
        forward_args=["group_by"],
    )
    mod.apply(cfg)
    assert [
        x["args"]["group_by"] for x in cfg["global_hooks"] if x["name"] == "raster-viz"
    ] == ["module", "source"]


def test_explicit_reporter_with_extra_args_is_respected(modifier_cls):
    cfg = {
        "global_hooks": [
            {"name": "stack-qc", "args": {"viz": True, "group_by": "module"}},
            {
                "name": "raster-viz",
                "args": {"group_by": "module", "output": "nice.html"},
            },
        ]
    }
    mod = modifier_cls(
        when={"hook": "stack-qc", "args": {"viz": True}},
        ensure={"name": "raster-viz"},
        forward_args=["group_by"],
    )
    mod.apply(cfg)
    assert len(cfg["global_hooks"]) == 2


def test_module_target_and_id_selector(modifier_cls):
    cfg = {
        "modules": [
            {
                "module": "local",
                "hooks": [
                    {"name": "filter", "id": "first"},
                    {"name": "filter", "id": "second"},
                ],
            }
        ]
    }
    mod = modifier_cls(
        when={"hook": "filter", "id": "second"},
        ensure={"name": "audit", "scope": "module"},
    )
    mod.apply(cfg)
    assert [h["name"] for h in cfg["modules"][0]["hooks"]] == [
        "filter",
        "filter",
        "audit",
    ]


def test_no_match_does_not_insert(modifier_cls):
    cfg = {"global_hooks": [{"name": "stack-qc", "args": {"viz": False}}]}
    modifier_cls(
        when={"hook": "stack-qc", "args": {"viz": True}}, ensure={"name": "raster-viz"}
    ).apply(cfg)
    assert len(cfg["global_hooks"]) == 1


def test_missing_or_bad_arguments_rejected(modifier_cls):
    with pytest.raises(ValueError):
        modifier_cls(when={}, ensure={"name": "raster-viz"})
    with pytest.raises(ValueError):
        modifier_cls(
            when={"hook": "stack-qc"},
            ensure={"name": "raster-viz", "stage": "finalize"},
        )
