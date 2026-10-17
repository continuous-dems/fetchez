"""Standalone reader regression tests; uses a lightweight BaseReader stub.

In the Fetchez tree, the same checks can instead import RasterReader directly.
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

from fetchez.streams.readers.raster import RasterReader


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
