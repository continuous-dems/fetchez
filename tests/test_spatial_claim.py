from types import SimpleNamespace

import pytest
import shapely

from fetchez.hooks.spatial_claim import SpatialClaimHook


def _entry(name, priority, geometry, required=True):
    return {
        "title": name,
        "claim_priority": priority,
        "claim_geometry": shapely.to_wkt(geometry),
        "claim_required": required,
    }


def _geom(entry, key="accepted_geometry"):
    return shapely.from_wkt(entry[key])


def test_partial_lower_priority_claim_keeps_only_unclaimed_area():
    high = _entry("high", 30, shapely.box(0, 0, 2, 1))
    low = _entry("low", 10, shapely.box(0, 0, 4, 1))

    result = SpatialClaimHook().run(
        [(SimpleNamespace(), low), (SimpleNamespace(), high)]
    )

    assert len(result) == 2
    assert _geom(high).equals(shapely.box(0, 0, 2, 1))
    assert _geom(low).equals(shapely.box(2, 0, 4, 1))
    assert shapely.from_wkt(low["excluded_geometry"]).equals(shapely.box(0, 0, 2, 1))


def test_equal_priority_sources_do_not_supersede_each_other():
    left = _entry("left", 2024, shapely.box(0, 0, 2, 1))
    right = _entry("right", 2024, shapely.box(1, 0, 3, 1))

    SpatialClaimHook().run([(SimpleNamespace(), left), (SimpleNamespace(), right)])

    assert _geom(left).intersection(_geom(right)).area == pytest.approx(1.0)
    assert "excluded_geometry" not in left
    assert "excluded_geometry" not in right


def test_existing_edition_exclusion_is_not_reaccepted_at_equal_priority():
    old = _entry("old edition", 200, shapely.box(0, 0, 3, 1))
    newer = _entry("new edition", 200, shapely.box(1, 0, 4, 1))
    old["excluded_geometry"] = shapely.to_wkt(shapely.box(1, 0, 3, 1))
    lower = _entry("lower", 100, shapely.box(0, 0, 5, 1))

    SpatialClaimHook().run(
        [
            (SimpleNamespace(), old),
            (SimpleNamespace(), newer),
            (SimpleNamespace(), lower),
        ]
    )

    assert _geom(old).equals(shapely.box(0, 0, 1, 1))
    assert _geom(old, "excluded_geometry").equals(shapely.box(1, 0, 3, 1))
    assert _geom(newer).equals(shapely.box(1, 0, 4, 1))
    assert _geom(lower).equals(shapely.box(4, 0, 5, 1))


def test_equal_numeric_priorities_with_different_types_do_not_exclude_peers():
    left = _entry("left", 600, shapely.box(0, 0, 2, 1))
    right = _entry("right", "600", shapely.box(1, 0, 3, 1))
    low = _entry("low", 100, shapely.box(0, 0, 4, 1))

    SpatialClaimHook().run(
        [
            (SimpleNamespace(), left),
            (SimpleNamespace(), right),
            (SimpleNamespace(), low),
        ]
    )

    assert _geom(left).intersection(_geom(right)).area == pytest.approx(1.0)
    assert _geom(low).equals(shapely.box(3, 0, 4, 1))
    assert "excluded_geometry" not in right


def test_non_finite_priority_is_rejected():
    entry = _entry("invalid", "NaN", shapely.box(0, 0, 1, 1))
    with pytest.raises(RuntimeError, match="finite priority"):
        SpatialClaimHook().run([(SimpleNamespace(), entry)])


def test_newer_priority_blocks_older_without_erasing_older_remainder():
    old = _entry("old", 2018, shapely.box(0, 0, 2, 1))
    new = _entry("new", 2024, shapely.box(1, 0, 3, 1))

    SpatialClaimHook().run([(SimpleNamespace(), old), (SimpleNamespace(), new)])

    assert _geom(new).equals(shapely.box(1, 0, 3, 1))
    assert _geom(old).equals(shapely.box(0, 0, 1, 1))
    assert shapely.from_wkt(old["excluded_geometry"]).equals(shapely.box(1, 0, 2, 1))


def test_interior_hole_in_authoritative_claim_remains_a_claim():
    # The authoritative footprint is the outer boundary. The hook must not use
    # valid-data pixels, so a lower tier receives only territory outside it.
    high = _entry("high", 30, shapely.box(0, 0, 2, 1))
    low = _entry("low", 10, shapely.box(0, 0, 3, 1))

    SpatialClaimHook().run([(SimpleNamespace(), high), (SimpleNamespace(), low)])

    assert _geom(low).intersection(shapely.box(0, 0, 2, 1)).area == 0
    assert _geom(low).equals(shapely.box(2, 0, 3, 1))


def test_missing_authoritative_geometry_fails_closed_for_targeted_entry():
    entry = {
        "claim_priority": 10,
        "claim_required": True,
        "title": "1_9as",
    }
    with pytest.raises(RuntimeError, match="authoritative geometry.*1_9as"):
        SpatialClaimHook().run([(SimpleNamespace(), entry)])


def test_unmarked_entries_pass_through_unchanged():
    other = {"title": "unrelated source"}
    result = SpatialClaimHook().run([(SimpleNamespace(), other)])
    assert result[0][1] is other


def test_fully_superseded_entry_is_dropped_but_claim_remains_for_lower_tiers():
    highest = _entry("highest", 30, shapely.box(0, 0, 2, 1))
    middle = _entry("middle", 20, shapely.box(0, 0, 1, 1))
    low = _entry("low", 10, shapely.box(0, 0, 3, 1))

    result = SpatialClaimHook().run(
        [
            (SimpleNamespace(), highest),
            (SimpleNamespace(), middle),
            (SimpleNamespace(), low),
        ]
    )

    assert [entry["title"] for _, entry in result] == ["highest", "low"]
    assert _geom(low).equals(shapely.box(2, 0, 3, 1))


def test_fallback_bbox_uses_fetchez_region_order():
    entry = {
        "bounds": (0, 2, 0, 1),
        "claim_priority": 1,
        "claim_required": True,
    }
    hook = SpatialClaimHook(fallback_bbox=True)
    hook.run([(SimpleNamespace(), entry)])
    assert shapely.from_wkt(entry["accepted_geometry"]).equals(shapely.box(0, 0, 2, 1))


def test_spatial_claim_audit_records_authoritative_and_accepted_geometry(tmp_path):
    import json
    import shapely
    from types import SimpleNamespace
    from fetchez.hooks.spatial_claim import SpatialClaimHook

    mod = SimpleNamespace(name="tnm")
    high = {
        "claim_priority": 10,
        "claim_geometry": "POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))",
        "claim_required": True,
        "claim_product": "high",
        "metadata": {"dataset": "high"},
    }
    low = {
        "claim_priority": 5,
        "claim_geometry": "POLYGON ((1 0, 3 0, 3 2, 1 2, 1 0))",
        "claim_required": True,
        "claim_product": "low",
        "metadata": {"dataset": "low"},
    }
    out = tmp_path / "claim.geojson"
    hook = SpatialClaimHook(audit_output=str(out))
    result = hook.run([(mod, high), (mod, low)])
    payload = json.loads(out.read_text())
    assert len(payload["features"]) == 2
    low_feature = next(
        f for f in payload["features"] if f["properties"]["dataset"] == "low"
    )
    claim = shapely.geometry.shape(low_feature["geometry"])
    accepted = shapely.from_wkt(low_feature["properties"]["accepted_wkt"])
    assert claim.area == 4.0
    assert accepted.area == 2.0
    assert low_feature["properties"]["product"] == "low"
    assert len(result) == 2
