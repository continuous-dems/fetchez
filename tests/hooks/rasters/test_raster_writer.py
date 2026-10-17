"""Standalone regression checks for RasterWrite and the generic RasterReader."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from fetchez.hooks.rasters.raster_writer import RasterWrite
from fetchez.streams.readers.raster import RasterReader


@pytest.fixture
def components():
    yield RasterReader, RasterWrite


@pytest.fixture
def samples(tmp_path):
    files = []
    for number in (1, 2):
        path = tmp_path / f"source{number}.tif"
        data = np.arange(3 * 8 * 10, dtype="float32").reshape(3, 8, 10) + number * 100
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=10,
            height=8,
            count=3,
            dtype="float32",
            nodata=-9999,
            transform=from_origin(10, 20, 1, 1),
            crs="EPSG:4326",
        ) as ds:
            ds.write(data)
            ds.update_tags(dataset="test")
            for i in range(1, 4):
                ds.set_band_description(i, f"band_{i}")
                ds.set_band_unit(i, "m")
        files.append((path, data))
    return files


def entry(reader, path, **kwargs):
    return (
        object(),
        {
            "dst_fn": str(path),
            "stream_type": "raster-stream",
            "stream": reader(str(path), **kwargs).yield_chunks(),
        },
    )


def test_multiband_buffered_drain(components, samples):
    Reader, Writer = components
    path, expected = samples[0]
    item = entry(Reader, path, buffer=2, chunk_size=4)
    Writer(drain=True).run([item])
    out = item[1]["dst_fn"]
    with rasterio.open(out) as ds:
        np.testing.assert_array_equal(ds.read(), expected)
        assert ds.descriptions == ("band_1", "band_2", "band_3")
        assert ds.units == ("m", "m", "m")
        assert ds.tags()["dataset"] == "test"
        assert ds.count == 3
    assert item[1]["artifacts"]["raster-write"] == out
    assert "stream" not in item[1]


def test_inline_first_chunk_and_chain(components, samples):
    Reader, Writer = components
    path, expected = samples[0]
    item = entry(Reader, path, chunk_size=4)
    upstream = item[1]["stream"]

    def altered():
        for chunk in upstream:
            chunk["data"] += 4
            yield chunk

    item[1]["stream"] = altered()
    Writer(drain=False).run([item])
    dest = str(path.with_name("source1_final.tif"))
    assert not __import__("os").path.exists(dest)
    observed = list(item[1]["stream"])
    assert len(observed) == 6
    with rasterio.open(dest) as ds:
        np.testing.assert_array_equal(ds.read(), expected + 4)
    assert item[1]["artifacts"]["raster-write"] == dest


def test_multiple_inputs_unique_output(components, samples, tmp_path):
    Reader, Writer = components
    items = [entry(Reader, path, chunk_size="full") for path, _ in samples]
    Writer(output_path=str(tmp_path) + "/", drain=True).run(items)
    for (_, entry_data), (_, expected) in zip(items, samples, strict=True):
        with rasterio.open(entry_data["dst_fn"]) as ds:
            np.testing.assert_array_equal(ds.read(), expected)
    assert items[0][1]["dst_fn"] != items[1][1]["dst_fn"]


def test_crop_with_buffer(components, samples):
    Reader, Writer = components
    path, expected = samples[0]

    class Region:
        srs = "EPSG:4326"

        def copy(self):
            return self

        def to_window(self, transform, width, height):
            return 2, 1, 4, 3

    item = entry(Reader, path, region=Region(), chunk_size=2, buffer=1)
    Writer(drain=True).run([item])
    with rasterio.open(item[1]["dst_fn"]) as ds:
        np.testing.assert_array_equal(ds.read(), expected[:, 1:4, 2:6])
        assert (ds.width, ds.height) == (4, 3)
        assert ds.transform == rasterio.windows.transform(
            rasterio.windows.Window(2, 1, 4, 3), from_origin(10, 20, 1, 1)
        )


def test_single_selected_band(components, samples):
    Reader, Writer = components
    path, expected = samples[0]
    item = entry(Reader, path, band_mode="single", bands=(3,), chunk_size=4)
    Writer(drain=True).run([item])
    with rasterio.open(item[1]["dst_fn"]) as ds:
        assert ds.count == 1
        np.testing.assert_array_equal(ds.read(1), expected[2])


def test_explicit_filename_multiple_raises(components, samples, tmp_path):
    Reader, Writer = components
    items = [entry(Reader, path) for path, _ in samples]
    with pytest.raises(ValueError, match="multiple entries"):
        Writer(output_path=str(tmp_path / "out.tif")).run(items)


def test_source_collision_is_protected(components, samples):
    Reader, Writer = components
    path, _ = samples[0]
    item = entry(Reader, path, chunk_size="full")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        Writer(output_path=str(path), drain=True).run([item])


def test_selected_stack_band_order_and_metadata(components, samples):
    Reader, Writer = components
    path, original = samples[0]
    item = entry(Reader, path, bands=(3, 1), chunk_size=4, buffer=1)
    Writer(drain=True).run([item])
    with rasterio.open(item[1]["dst_fn"]) as ds:
        assert ds.count == 2
        np.testing.assert_array_equal(ds.read(), original[[2, 0]])
        assert ds.descriptions == ("band_3", "band_1")
        assert ds.units == ("m", "m")


def test_template_outputs(components, samples, tmp_path):
    Reader, Writer = components
    items = [entry(Reader, path, chunk_size="full") for path, _ in samples]
    Writer(output_path=str(tmp_path / "{stem}_{index}.tif"), drain=True).run(items)
    assert [__import__("os").path.basename(item[1]["dst_fn"]) for item in items] == [
        "source1_0.tif",
        "source2_1.tif",
    ]


def test_no_published_artifact_before_inline_complete(components, samples):
    Reader, Writer = components
    path, original = samples[0]
    item = entry(Reader, path, chunk_size=4)
    Writer(drain=False).run([item])
    generator = item[1]["stream"]
    next(generator)
    assert not path.with_name("source1_final.tif").exists()
    assert "artifacts" not in item[1]
    list(generator)
    assert path.with_name("source1_final.tif").exists()
