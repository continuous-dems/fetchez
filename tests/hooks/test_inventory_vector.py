"""Offline tests for the vector-capable inventory finalizer."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from fetchez.hooks.inventory import Inventory


@pytest.fixture
def module():
    return SimpleNamespace(name="tnm", instance_id="coverage_a")


def test_geojson_mixed_and_null_footprints(tmp_path, module):
    poly = box(-120, 33, -119, 34)
    entries = [
        (module, {"dst_fn": "a.tif", "geometry": poly, "metadata": {"resolution": 1}}),
        (module, {"dst_fn": "b.tif"}),
    ]
    path = tmp_path / "inventory.geojson"
    assert Inventory(output=path).run(entries) is entries
    result = json.loads(path.read_text())
    assert [f["geometry"] is None for f in result["features"]] == [False, True]
    assert result["features"][0]["properties"]["module"] == "tnm"
    assert result["features"][0]["properties"]["instance_id"] == "coverage_a"
    assert entries[0][1]["geometry"] is poly
    assert json.loads(result["features"][0]["properties"]["metadata_json"])[
        "metadata"
    ] == {"resolution": 1}


def test_geometry_required_filters_only_output(tmp_path, module):
    entries = [
        (module, {"dst_fn": "missing"}),
        (module, {"geometry": box(-1, -1, 1, 1)}),
    ]
    path = tmp_path / "required.geojson"
    Inventory(output=path, geometry_required=True).run(entries)
    assert len(json.loads(path.read_text())["features"]) == 1
    assert len(entries) == 2


def test_gpkg_roundtrip_and_empty(tmp_path, module):
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")
    path = tmp_path / "inventory.gpkg"
    entries = [
        (module, {"geometry": box(-122, 32, -121, 33)}),
        (module, {"dst_fn": "unknown"}),
    ]
    Inventory(output=path, layer="footprints").run(entries)
    frame = gpd.read_file(path, layer="footprints")
    assert len(frame) == 2
    assert frame.crs.to_epsg() == 4326
    assert sum(geom is None for geom in frame.geometry) == 1
    Inventory(output=path).run([])
    assert len(gpd.read_file(path, layer="footprints")) == 0


def test_projected_geometry_reprojects_if_crs_is_provided(tmp_path, module):
    from pyproj import Transformer
    from shapely.ops import transform

    geographic = box(-120, 33, -119, 34)
    projected = transform(
        Transformer.from_crs(4326, 3857, always_xy=True).transform, geographic
    )
    entry = {"geometry": projected, "geometry_crs": "EPSG:3857"}
    path = tmp_path / "projected.geojson"
    Inventory(output=path).run([(module, entry)])
    coords = json.loads(path.read_text())["features"][0]["geometry"]["coordinates"][0]
    assert min(p[0] for p in coords) == pytest.approx(-120)
    assert min(p[1] for p in coords) == pytest.approx(33)


def test_json_handles_shapely_and_nested_metadata(tmp_path, module):
    entry = {
        "geometry": box(-120, 33, -119, 34),
        "metadata": {"path": Path("tile.tif")},
    }
    path = tmp_path / "inventory.json"
    Inventory(output=path).run([(module, entry)])
    data = json.loads(path.read_text())
    assert data[0]["geometry"]["type"] == "Polygon"
    assert data[0]["metadata"]["path"] == "tile.tif"
    assert entry["metadata"]["path"] == Path("tile.tif")


def test_unknown_crs_with_out_of_range_geometry_fails(tmp_path, module):
    with pytest.raises(ValueError, match="geometry_crs"):
        Inventory(output=tmp_path / "invalid.geojson").run(
            [(module, {"geometry": box(500000, 3700000, 501000, 3701000)})]
        )
