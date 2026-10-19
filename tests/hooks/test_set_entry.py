"""Focused behavior tests for the generic set-entry hook."""

from types import SimpleNamespace

import pytest
from fetchez.hooks.set_result_entry import SetEntryKey


def entries():
    return [
        (
            SimpleNamespace(name="icesat2"),
            {"dst_fn": "/data/ATL03_A.h5", "data_type": "hdf5"},
        ),
        (
            SimpleNamespace(name="tnm"),
            {"dst_fn": "/data/dem.tif", "data_type": "raster"},
        ),
    ]


def test_profile_rules_by_extension():
    data = entries()
    SetEntryKey(key="profile", rules={"*.h5": "atl03", "*.tif": "rasterio"}).run(data)
    assert [e["profile"] for _, e in data] == ["atl03", "rasterio"]


def test_module_matching():
    data = entries()
    SetEntryKey(key="profile", match_key="module", rules={"icesat2": "atl03"}).run(data)
    assert data[0][1]["profile"] == "atl03"
    assert "profile" not in data[1][1]


def test_existing_value_preserved_unless_overwrite():
    data = entries()
    data[0][1]["profile"] = "existing"
    SetEntryKey(key="profile", value="new").run(data)
    assert data[0][1]["profile"] == "existing"
    SetEntryKey(key="profile", value="new", overwrite=True).run(data)
    assert data[0][1]["profile"] == "new"


def test_inline_profile_deep_copied():
    data = entries()
    profile = {"reader": {"name": "atl03", "args": {"bands": [1, 2]}}}
    SetEntryKey(key="profile", value=profile).run(data)
    data[0][1]["profile"]["reader"]["args"]["bands"].append(3)
    assert data[1][1]["profile"]["reader"]["args"]["bands"] == [1, 2]
    assert profile["reader"]["args"]["bands"] == [1, 2]


def test_unmatched_and_default():
    data = entries()
    SetEntryKey(key="tag", rules={"*.zip": "archive"}).run(data)
    assert all("tag" not in e for _, e in data)
    SetEntryKey(key="tag", rules={"*.h5": "satellite"}, default="other").run(data)
    assert [e["tag"] for _, e in data] == ["satellite", "other"]


def test_match_single_pattern_and_arbitrary_key():
    data = entries()
    SetEntryKey(key="src_srs", match="*.tif", value="EPSG:4326").run(data)
    assert "src_srs" not in data[0][1]
    assert data[1][1]["src_srs"] == "EPSG:4326"


def test_rule_order_and_preserved_types():
    data = entries()
    SetEntryKey(key="priority", rules={"*.h5": 3, "ATL03_*": 4}, default=1).run(data)
    assert [e["priority"] for _, e in data] == [3, 1]


def test_invalid_configuration():
    with pytest.raises(ValueError):
        SetEntryKey(value="x")
    with pytest.raises(ValueError):
        SetEntryKey(key="profile", match="*.h5")
