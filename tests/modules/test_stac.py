"""Offline regression tests for fetchez.modules.stac.

Uses normal package imports; no external catalog or network traffic.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from shapely.geometry import Polygon, shape

from fetchez.hooks.inventory import Inventory
from fetchez.modules.stac import STACModule, STAC_3DEP_Seamless, STAC_3DEP_Lidar


class FakeAsset:
    def __init__(self, href, media_type="image/tiff", roles=("data",)):
        self.href = href
        self.media_type = media_type
        self.roles = list(roles)


class FakeItem:
    id = "tile:1"
    collection_id = "cop-dem-glo-30"
    datetime = datetime(2025, 1, 2, tzinfo=timezone.utc)
    bbox = [-118, 32, -117, 33]
    geometry = None
    properties = {"proj:epsg": 4326}
    assets = {
        "data": FakeAsset("https://example.org/dem.tif?token=123"),
        "thumbnail": FakeAsset(
            "https://example.org/thumb.jpg", "image/jpeg", ("thumbnail",)
        ),
    }


def make_module(**kwargs):
    # The module base accepts region as a normal option; these tests avoid live services.
    kwargs.setdefault("use_cache", False)
    return STACModule(**kwargs)


def test_lists_from_cli_or_yaml():
    a = make_module(collections=" cop-dem-glo-30, sentinel-2 ", assets="data,thumbnail")
    b = make_module(
        collections=["cop-dem-glo-30", "sentinel-2"], assets=["data", "thumbnail"]
    )
    assert a.collections == b.collections
    assert a.asset_keys == b.asset_keys


def test_unbounded_requires_constraint():
    module = make_module()
    with pytest.raises(ValueError, match="Unbounded"):
        module._build_search()
    assert "bbox" not in make_module(collections="cop-dem-glo-30")._build_search()


def test_cloud_cover_and_generic_query():
    module = make_module(
        collections="test", cloud_cover=15, query={"proj:epsg": {"eq": 4326}}
    )
    params = module._build_search()
    assert params["query"]["eo:cloud_cover"] == {"lt": 15}
    assert params["query"]["proj:epsg"] == {"eq": 4326}
    with pytest.raises(ValueError, match="conflicts"):
        make_module(cloud_cover=10, query={"eo:cloud_cover": {"lt": 50}})


def test_asset_selection_and_filtering():
    item = FakeItem()
    assert [key for key, _ in make_module()._select_assets(item)] == ["data"]
    assert {key for key, _ in make_module(assets="all")._select_assets(item)} == {
        "data",
        "thumbnail",
    }
    assert [
        key for key, _ in make_module(asset_roles=["thumbnail"])._select_assets(item)
    ] == ["thumbnail"]
    assert [
        key
        for key, _ in make_module(
            assets="all", asset_media_types="image/tiff"
        )._select_assets(item)
    ] == ["data"]


def test_filename_and_metadata(monkeypatch):
    module = make_module(assets="data", sign="none")
    recorded = []
    monkeypatch.setattr(
        module, "add_entry_to_results", lambda **kw: recorded.append(kw)
    )
    module._asset_to_entry(FakeItem(), "data", FakeItem.assets["data"], {})
    entry = recorded[0]
    assert entry["dst_fn"].endswith("_data.tif")
    assert "?" not in entry["dst_fn"]
    assert entry["data_type"] == "raster"
    assert entry["metadata"]["stac_properties"]["proj:epsg"] == 4326
    assert entry["metadata"]["stac_id"] == "tile:1"


def test_non_raster_type(monkeypatch):
    module = make_module(sign="none")
    recorded = []
    monkeypatch.setattr(
        module, "add_entry_to_results", lambda **kw: recorded.append(kw)
    )
    module._asset_to_entry(
        FakeItem(),
        "points",
        FakeAsset("https://a.org/points.copc.laz", "application/vnd.laszip+copc"),
        {},
    )
    assert recorded[0]["data_type"] == "point_cloud"
    assert recorded[0]["dst_fn"].endswith(".copc.laz")


def test_presets_construct_without_kwargs():
    a = STAC_3DEP_Seamless()
    b = STAC_3DEP_Lidar()
    assert a.collections == ["3dep-seamless"]
    assert b.collections == ["3dep-lidar-copc"]
    assert STAC_3DEP_Seamless(collections="override").collections == ["override"]


def test_run_uses_catalog_search(monkeypatch):
    import fetchez.modules.stac as stac_mod

    module = make_module(
        collections="cop-dem-glo-30", assets="data", sign="none", limit=2
    )
    entries = []
    monkeypatch.setattr(module, "add_entry_to_results", lambda **kw: entries.append(kw))
    catalog = MagicMock()
    catalog.search.return_value.items.return_value = iter([FakeItem()])
    monkeypatch.setattr(module, "_open_catalog", lambda: catalog)
    monkeypatch.setattr(stac_mod, "pystac_client", SimpleNamespace())
    assert module.run() is module
    assert len(entries) == 1
    assert catalog.search.call_args.kwargs["collections"] == ["cop-dem-glo-30"]
    assert "bbox" not in catalog.search.call_args.kwargs


def test_item_footprint_survives_discovery_cache_and_inventory(monkeypatch, tmp_path):
    import fetchez.modules.stac as stac_mod

    item = FakeItem()
    item.geometry = {
        "type": "Polygon",
        "coordinates": [[[-118, 32], [-117, 32], [-117, 33], [-118, 32]]],
    }
    item.properties = {"proj:epsg": 32611}
    footprint = Polygon(item.geometry["coordinates"][0])
    catalog = MagicMock()
    catalog.search.return_value.items.return_value = [item]
    monkeypatch.setattr(stac_mod, "pystac_client", SimpleNamespace())
    module_options = {
        "collections": "cop-dem-glo-30",
        "assets": "all",
        "sign": "none",
        "outdir": tmp_path,
        "use_cache": True,
    }

    first = make_module(**module_options)
    monkeypatch.setattr(first, "_open_catalog", lambda: catalog)
    first.run()
    assert len(first.results) == 2
    for entry in first.results:
        assert entry["geometry"].equals(footprint)
        assert entry["geometry_crs"] == "EPSG:4326"
        assert entry["geometry_source"] == "stac_item_geometry"
        assert entry["geometry_kind"] == "footprint"
        assert entry["geometry_type"] == "Polygon"

    cached = make_module(**module_options)
    open_catalog = MagicMock(side_effect=AssertionError("Expected a cache hit"))
    monkeypatch.setattr(cached, "_open_catalog", open_catalog)
    cached.run()
    open_catalog.assert_not_called()
    assert all(not Path(entry["dst_fn"]).exists() for entry in cached.results)

    output = tmp_path / "stac.geojson"
    Inventory(output=output, geometry_required=True).run(
        [(cached, entry) for entry in cached.results]
    )
    features = json.loads(output.read_text(encoding="utf-8"))["features"]
    assert len(features) == 2
    for feature in features:
        assert shape(feature["geometry"]).equals(footprint)
        assert feature["properties"]["geometry_source"] == "stac_item_geometry"


def test_run_omits_missing_or_invalid_footprints(monkeypatch):
    import fetchez.modules.stac as stac_mod

    nonspatial = FakeItem()
    nonspatial.bbox = None
    malformed = FakeItem()
    malformed.geometry = {"type": "Polygon"}
    valid = FakeItem()
    valid.geometry = {"type": "Point", "coordinates": [-118, 32]}
    catalog = MagicMock()
    catalog.search.return_value.items.return_value = [nonspatial, malformed, valid]
    module = make_module(collections="test", sign="none")
    monkeypatch.setattr(module, "_open_catalog", lambda: catalog)
    monkeypatch.setattr(stac_mod, "pystac_client", SimpleNamespace())
    module.run()

    assert module._discovery_failed is False
    assert len(module.results) == 3
    assert "geometry" not in module.results[0]
    assert "geometry" not in module.results[1]
    assert module.results[2]["geometry_type"] == "Point"


def test_missing_dependency_fails_discovery(monkeypatch):
    import fetchez.modules.stac as stac_mod

    monkeypatch.setattr(stac_mod, "pystac_client", None)
    module = make_module(collections="test")
    assert module.run() is module
    assert module._discovery_failed is True


def test_signed_s3_fallback(monkeypatch):
    import fetchez.modules.stac as stac_mod

    monkeypatch.setattr(stac_mod, "boto3", None)
    module = make_module(sign="s3")
    assert module._resolve_asset_url(FakeAsset("s3://some-bucket/file.tif")) == (
        "https://some-bucket.s3.amazonaws.com/file.tif"
    )
