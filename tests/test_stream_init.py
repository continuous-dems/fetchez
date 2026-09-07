from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pyproj import CRS
from pyproj.crs import CompoundCRS

from fetchez.hooks.stream_init import DataStream
from fetchez.spatial import Region


@pytest.mark.parametrize(
    "source",
    [
        "EPSG:4269",
        CRS(4269).to_wkt("WKT1_GDAL"),
        CRS(6350).to_wkt(),
        CRS.from_proj4("+proj=longlat +datum=NAD83").to_wkt(),
    ],
)
def test_stream_adds_vertical_reference(monkeypatch, source):
    entry = initialize(monkeypatch, source)
    crs = CRS(entry["src_srs"])
    assert crs.is_compound
    assert crs.sub_crs_list[0].equals(CRS(source))
    assert crs.sub_crs_list[1].equals(CRS(5703))


@pytest.mark.parametrize(
    "source",
    [
        CRS(4979).to_wkt(),
        CompoundCRS("Albers + height", [CRS(6350), CRS(5703)]).to_wkt(),
    ],
)
def test_stream_preserves_existing_vertical_reference(monkeypatch, source):
    assert initialize(monkeypatch, source)["src_srs"] == source


def test_stream_preserves_custom_vertical_reference(monkeypatch):
    assert (
        initialize(monkeypatch, "EPSG:4326", "global:mss")["src_srs"]
        == "EPSG:4326+global:mss"
    )


def initialize(monkeypatch, source, vertical="EPSG:5703"):
    from fetchez.hooks import stream_init

    reader = SimpleNamespace(
        name="test", get_srs=lambda: source, yield_chunks=lambda: iter([1])
    )
    monkeypatch.setattr(stream_init.ReaderRegistry, "load_all", Mock())
    monkeypatch.setattr(stream_init.ProfileRegistry, "load_all", Mock())
    monkeypatch.setattr(
        stream_init.ReaderRegistry, "get_reader", lambda *args, **kwargs: reader
    )
    entry = {"dst_fn": "dem.tif"}
    module = SimpleNamespace(region=Region(-67.001, -67, 44.9, 44.901))
    DataStream(vert_srs=vertical).run([(module, entry)])
    return entry
