"""Standalone reader regression tests; uses a lightweight BaseReader stub.

In the Fetchez tree, the same checks can instead import RasterReader directly.
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

from fetchez.streams.readers.raster import RasterReader
from fetchez.registry import ReaderRegistry, ProfileRegistry, DataTypeRegistry
from fetchez.spatial import Region

TRANSFORM = from_origin(-124.0, 42.0, 0.01, 0.01)


@pytest.fixture(scope="module")
def reader_cls():
    yield RasterReader


@pytest.fixture
def raster(tmp_path):
    path = tmp_path / "sample.tif"
    data = np.arange(2 * 8 * 10, dtype="float32").reshape(2, 8, 10)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=8,
        count=2,
        dtype="float32",
        nodata=-9999,
        transform=from_origin(100, 50, 2, 2),
        crs="EPSG:4326",
    ) as dst:
        dst.write(data)
    return path, data


def test_existing_chunk_fields(reader_cls, raster):
    path, original = raster
    chunks = list(reader_cls(str(path), chunk_size=4).yield_chunks())
    assert len(chunks) == 6
    assert all(c["data"].ndim == 3 for c in chunks)
    assert np.array_equal(chunks[0]["data"], original[:, :4, :4])
    assert chunks[0]["window"] == chunks[0]["read_window"]
    assert chunks[0]["context"] is chunks[-1]["context"]
    context = chunks[0]["context"]
    assert context.profile["count"] == 2
    assert context.profile["width"] == 10
    assert context.source_profile["height"] == 8
    assert context.source.endswith("sample.tif")
    assert context.metadata["selection_window"] == Window(0, 0, 10, 8)


def test_full_window(reader_cls, raster):
    path, original = raster
    chunks = list(reader_cls(str(path), chunk_size="full").yield_chunks())
    assert len(chunks) == 1
    assert chunks[0]["window"] == Window(0, 0, 10, 8)
    assert np.array_equal(chunks[0]["data"], original)
    assert len(list(reader_cls(str(path), chunk_size=-1).yield_chunks())) == 1


def test_buffer_and_transform(reader_cls, raster):
    path, original = raster
    chunks = list(reader_cls(str(path), chunk_size=4, buffer=2).yield_chunks())
    first = chunks[0]
    assert first["window"] == Window(0, 0, 4, 4)
    assert first["read_window"] == Window(0, 0, 6, 6)
    assert np.array_equal(first["data"], original[:, :6, :6])
    middle = next(
        c for c in chunks if c["window"].col_off == 4 and c["window"].row_off == 4
    )
    assert middle["read_window"] == Window(2, 2, 8, 6)
    assert np.array_equal(middle["data"], original[:, 2:8, 2:10])
    with rasterio.open(path) as src:
        assert middle["transform"] == src.window_transform(middle["read_window"])
        # Restore exactly the core extent after processing a halo.
        x = int(middle["window"].col_off - middle["read_window"].col_off)
        y = int(middle["window"].row_off - middle["read_window"].row_off)
        assert np.array_equal(
            middle["data"][:, y : y + 4, x : x + 4], original[:, 4:8, 4:8]
        )


def test_single_mode(reader_cls, raster):
    path, original = raster
    chunks = list(
        reader_cls(
            str(path), bands=(2,), band_mode="single", chunk_size="full"
        ).yield_chunks()
    )
    assert len(chunks) == 1
    assert chunks[0]["band_index"] == 2
    assert chunks[0]["context"].profile["count"] == 1
    assert np.array_equal(chunks[0]["data"], original[1])
    assert chunks[0]["mask"].shape == original[1].shape


def test_metadata_is_independent_from_source(reader_cls, raster):
    path, _ = raster
    chunk = next(reader_cls(str(path), chunk_size="full").yield_chunks())
    context = chunk["context"]
    context.profile["count"] = 1
    context.metadata["processed"] = True
    assert context.source_profile["count"] == 2


@pytest.mark.parametrize("size", [0, -2, "wrong", (3, 0), True])
def test_bad_size(reader_cls, size):
    with pytest.raises(ValueError):
        reader_cls("dummy.tif", chunk_size=size)


def test_bad_buffer(reader_cls):
    with pytest.raises(ValueError):
        reader_cls("dummy.tif", buffer=-1)


def test_selected_region_full_and_buffer(reader_cls, raster):
    path, original = raster

    class Region:
        srs = "EPSG:4326"

        def copy(self):
            return self

        def to_window(self, transform, width, height):
            return (2, 1, 4, 3)

    (chunk,) = list(
        reader_cls(
            str(path), region=Region(), chunk_size="full", buffer=1
        ).yield_chunks()
    )
    assert chunk["window"] == Window(2, 1, 4, 3)
    assert chunk["read_window"] == Window(1, 0, 6, 5)
    assert np.array_equal(chunk["data"], original[:, :5, 1:7])
    assert chunk["context"].profile["width"] == 4
    assert chunk["context"].profile["height"] == 3
    with rasterio.open(path) as src:
        assert chunk["context"].profile["transform"] == src.window_transform(
            chunk["window"]
        )


def test_hook_chain_data_and_context(reader_cls, raster):
    path, original = raster
    processed = []
    for chunk in reader_cls(str(path), chunk_size=4).yield_chunks():
        # Two independent operations; downstream sees the previous result.
        chunk["data"] = chunk["data"] + 3
        chunk["data"] = chunk["data"] * 2
        processed.append(chunk)
    assert np.array_equal(processed[0]["data"], (original[:, :4, :4] + 3) * 2)
    assert all(chunk["context"] is processed[0]["context"] for chunk in processed)


@pytest.fixture
def raster_file(tmp_path):
    path = tmp_path / "multi.tif"
    data = np.stack(
        [
            np.arange(35, dtype="float32").reshape(5, 7) + 10 * band
            for band in range(1, 4)
        ]
    )
    data[0, 0, 0] = -9999
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=5,
        width=7,
        count=3,
        dtype="float32",
        crs="EPSG:4326",
        transform=TRANSFORM,
        nodata=-9999,
    ) as dst:
        dst.write(data)
    return path, data


def _reassemble(chunks, shape=(5, 7), bands=(1, 2, 3)):
    out = np.full((len(bands), *shape), np.nan, dtype="float32")
    for chunk in chunks:
        w = chunk["window"]
        r, c = int(w.row_off), int(w.col_off)
        h, width = int(w.height), int(w.width)
        if "band_indices" in chunk:
            for pos, band in enumerate(chunk["band_indices"]):
                out[bands.index(band), r : r + h, c : c + width] = chunk["data"][pos]
        else:
            band = chunk["band_index"]
            out[bands.index(band), r : r + h, c : c + width] = chunk["data"]
    return out


@pytest.mark.parametrize("mode", ["single", "stack"])
def test_windowed_multiband_roundtrip(raster_file, mode):
    path, expected = raster_file
    chunks = list(RasterReader(str(path), chunk_size=3, band_mode=mode).yield_chunks())
    assert chunks
    np.testing.assert_array_equal(_reassemble(chunks), expected)
    for chunk in chunks:
        w = chunk["window"]
        assert w.width <= 3 and w.height <= 3
        assert chunk["crs"].to_epsg() == 4326
        assert chunk["transform"] == rasterio.windows.transform(w, TRANSFORM)
        if mode == "stack":
            assert chunk["data"].ndim == 3
            assert chunk["data"].shape[0] == len(chunk["band_indices"])
            assert chunk["data"].shape[1:] == (int(w.height), int(w.width))
        else:
            assert chunk["data"].ndim == 2
            assert chunk["band_index"] in (1, 2, 3)


def test_selected_bands_keep_original_numbers(raster_file):
    path, data = raster_file
    chunks = list(
        RasterReader(
            str(path), chunk_size=4, band_mode="stack", bands=[3, 1]
        ).yield_chunks()
    )
    assert chunks
    assert all(tuple(c["band_indices"]) == (3, 1) for c in chunks)
    np.testing.assert_array_equal(
        _reassemble(chunks, bands=(3, 1)),
        data[[2, 0]],
    )


def test_mask_and_nodata(raster_file):
    path, _ = raster_file
    chunks = list(
        RasterReader(
            str(path),
            chunk_size=3,
            band_mode="stack",
            bands=[1],
            include_mask=True,
        ).yield_chunks()
    )
    first = chunks[0]
    assert first["mask"].shape == first["data"].shape
    assert first["mask"][0, 0, 0] == 0
    assert first["data"][0, 0, 0] == -9999
    assert first["nodata"][0] == -9999


def test_region_cropping(raster_file):
    path, _ = raster_file
    # Exact pixel-aligned bounds: columns 2:5, rows 1:4.

    region = Region(-123.98, -123.95, 41.96, 41.99)
    xcount, ycount, dst_gt = region.geo_transform(
        x_inc=0.01,
        y_inc=0.01,
        node="grid",
    )
    chunks = list(
        RasterReader(
            str(path),
            region=region,
            chunk_size=2,
            band_mode="stack",
        ).yield_chunks()
    )
    assert chunks
    assert all(c["window"].col_off >= 2 for c in chunks)
    assert all(c["window"].row_off >= 1 for c in chunks)
    assert all(c["window"].col_off + c["window"].width <= 5 for c in chunks)
    assert all(c["window"].row_off + c["window"].height <= 4 for c in chunks)


def test_nonoverlapping_region_yields_nothing(raster_file):
    path, _ = raster_file
    reader = RasterReader(str(path), region=[0, 1, 0, 1], band_mode="stack")
    assert list(reader.yield_chunks()) == []


def test_reader_registry_resolves_explicit_inline_profile(raster_file):
    path, _ = raster_file
    ReaderRegistry.load_all()
    profile = {
        "name": "test-inline-raster",
        "data_type": "raster",
        "reader": {
            "name": "rasterio",
            "args": {"band_mode": "stack", "bands": [2]},
        },
    }
    entry = {"dst_fn": str(path), "data_type": "raster", "profile": profile}
    reader = ReaderRegistry.get_reader_from_entry(entry)
    assert isinstance(reader, RasterReader)
    chunk = next(reader.yield_chunks())
    assert tuple(chunk["band_indices"]) == (2,)
    assert entry["profile"] == profile


def test_registered_profile_resolution(raster_file):
    path, _ = raster_file
    ProfileRegistry.load_all()
    ReaderRegistry.load_all()
    profile = ProfileRegistry.resolve("rasterio")
    assert profile is not None, "The rasterio.yaml profile must be installed"
    assert profile["reader"]["name"] == "rasterio"
    reader = ReaderRegistry.get_reader_from_entry(
        {
            "dst_fn": str(path),
            "data_type": "raster",
            "profile": "rasterio",
        }
    )
    assert isinstance(reader, RasterReader)


def test_datatype_default_profile_resolution(raster_file, monkeypatch):
    path, _ = raster_file
    ReaderRegistry.load_all()
    # Isolate this test from the installed raster data-type YAML defaults.
    profile = {"reader": {"name": "rasterio", "args": {"band_mode": "stack"}}}
    monkeypatch.setattr(
        DataTypeRegistry,
        "get_default_profile",
        classmethod(lambda cls, name: profile if name == "raster" else None),
    )
    reader = ReaderRegistry.get_reader_from_entry(
        {
            "dst_fn": str(path),
            "data_type": "raster",
        }
    )
    assert isinstance(reader, RasterReader)
    assert next(reader.yield_chunks())["data"].ndim == 3


def test_reader_declares_raster_stream():
    assert RasterReader.meta_produces == "raster-stream"


def test_region_cropping_aligned(raster_file):
    path, _ = raster_file

    region = Region(-123.98, -123.95, 41.96, 41.99)

    chunks = list(
        RasterReader(
            str(path),
            region=region,
            chunk_size=2,
            band_mode="stack",
        ).yield_chunks()
    )

    windows = [chunk["window"] for chunk in chunks]

    assert min(w.col_off for w in windows) == 2
    assert min(w.row_off for w in windows) == 1
    assert max(w.col_off + w.width for w in windows) == 5
    assert max(w.row_off + w.height for w in windows) == 4

    first = min(
        chunks,
        key=lambda c: (
            c["window"].row_off,
            c["window"].col_off,
        ),
    )

    x, y = first["transform"] * (0.5, 0.5)

    assert x == pytest.approx(-123.975)
    assert y == pytest.approx(41.985)


def test_region_cropping_fractional(raster_file):
    path, _ = raster_file

    region = Region(-123.985, -123.955, 41.955, 41.985)

    chunks = list(
        RasterReader(
            str(path),
            region=region,
            chunk_size=2,
            band_mode="stack",
        ).yield_chunks()
    )

    windows = [chunk["window"] for chunk in chunks]

    assert min(w.col_off for w in windows) == 1
    assert min(w.row_off for w in windows) == 1
    assert max(w.col_off + w.width for w in windows) == 5
    assert max(w.row_off + w.height for w in windows) == 5
