"""Standalone tests; import the inventory hook with a minimal FetchHook stub."""

import json
from types import SimpleNamespace

import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from fetchez.hooks.inventory import Inventory


def entries():
    module = SimpleNamespace(name="survey", instance_id="entry_1")
    return [
        (
            module,
            {
                "url": "a",
                "data_type": "point",
                "dst_fn": "a",
                "geometry": Point(-119, 34),
                "geometry_kind": "station_location",
                "geometry_source": "provider",
            },
        ),
        (
            module,
            {
                "url": "b",
                "data_type": "line",
                "dst_fn": "b",
                "geometry": LineString([(-119, 34), (-118, 35)]),
                "geometry_kind": "trackline",
            },
        ),
        (
            module,
            {
                "url": "c",
                "data_type": "polygon",
                "dst_fn": "c",
                "geometry": MultiPolygon(
                    [Polygon([(-120, 33), (-119, 33), (-119, 34)])]
                ),
                "geometry_kind": "survey_coverage",
            },
        ),
        (module, {"url": "d", "data_type": "unknown", "dst_fn": "d"}),
    ]


def test_mixed_gpkg(tmp_path):
    hook = Inventory(output=tmp_path / "mixed.gpkg")
    src = entries()
    assert hook.run(src) is src
    table = gpd.read_file(tmp_path / "mixed.gpkg")
    assert table.geom_type.fillna("NULL").tolist() == [
        "Point",
        "LineString",
        "MultiPolygon",
        "NULL",
    ]
    assert table.geometry_type.fillna("NULL").tolist() == [
        "Point",
        "LineString",
        "MultiPolygon",
        "NULL",
    ]
    assert table.geometry_kind.iloc[0] == "station_location"
    assert table.geometry_kind.iloc[1] == "trackline"


def test_mixed_geojson(tmp_path):
    hook = Inventory(output=tmp_path / "mixed.geojson")
    hook.run(entries())
    data = json.loads((tmp_path / "mixed.geojson").read_text())
    assert [
        f["geometry"]["type"] if f["geometry"] else None for f in data["features"]
    ] == ["Point", "LineString", "MultiPolygon", None]
    assert data["features"][0]["properties"]["geometry_kind"] == "station_location"


def test_only_with_geometry(tmp_path):
    hook = Inventory(output=tmp_path / "only.geojson", geometry_required=True)
    hook.run(entries())
    data = json.loads((tmp_path / "only.geojson").read_text())
    assert len(data["features"]) == 3
