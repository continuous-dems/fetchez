"""Integration tests for the installed/editable Fetchez raster pipeline.

Run from the repository root with: python -m pytest tests/test_raster_pipeline.py -q
Place RasterPipeline at fetchez/hooks/rasters/raster_pipeline.py and RasterHook
at fetchez/hooks/raster.py (adjust the import if the base lives elsewhere).
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from fetchez.hooks.rasters.base import RasterHook
from fetchez.hooks.rasters.raster_pipeline import RasterPipeline


class AddRaster(RasterHook):
    """Test-only unregistered hook: makes changes easy to verify."""

    name = "test-raster-add"

    def __init__(self, amount=1, **kwargs):
        super().__init__(**kwargs)
        self.amount = amount

    def process_chunk(self, chunk, entry):
        return {**chunk, "data": chunk["data"] + self.amount}


def make_file(path, offset=0):
    data = np.arange(3 * 8 * 10, dtype="float32").reshape(3, 8, 10) + offset
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=10,
        count=3,
        dtype="float32",
        nodata=-9999,
        transform=from_origin(10, 20, 1, 1),
        crs="EPSG:4326",
    ) as dst:
        dst.write(data)
        dst.update_tags(dataset="composite-test")
        for band in range(1, 4):
            dst.set_band_description(band, f"band_{band}")
            dst.set_band_unit(band, "m")
    return data


@pytest.mark.parametrize("stage", ["file", "collection"])
def test_stage_multiband_and_chained_hooks(tmp_path, stage):
    source = tmp_path / "source.tif"
    original = make_file(source)
    entry = {"dst_fn": str(source), "data_type": "raster"}
    pipeline = RasterPipeline(
        stage=stage,
        reader={"chunk_size": 3, "buffer": 1},
        hooks=[{"name": AddRaster, "args": {"amount": 3}}, AddRaster(amount=7)],
        writer={"suffix": "_filtered"},
    )
    assert pipeline.stage == stage
    rows = pipeline.run([(object(), entry)])
    assert rows[0][1] is entry
    assert "stream" not in entry
    assert str(entry["dst_fn"]).endswith("source_filtered.tif")
    with rasterio.open(entry["dst_fn"]) as out:
        np.testing.assert_array_equal(out.read(), original + 10)
        assert out.descriptions == ("band_1", "band_2", "band_3")
        assert out.tags()["dataset"] == "composite-test"
    with rasterio.open(source) as original_ds:
        np.testing.assert_array_equal(original_ds.read(), original)


def test_many_entries_and_skipping_unrelated(tmp_path):
    entries = []
    for n in (1, 2):
        source = tmp_path / f"input{n}.tif"
        expected = make_file(source, offset=n * 100)
        entries.append(
            (
                object(),
                {"dst_fn": str(source), "data_type": "raster", "expected": expected},
            )
        )
    unrelated = (
        object(),
        {"dst_fn": str(tmp_path / "metadata.csv"), "data_type": "table"},
    )
    entries.insert(1, unrelated)
    pipeline = RasterPipeline(
        hooks=[AddRaster],
        reader={"chunk_size": "full"},
        writer={"output_path": str(tmp_path / "processed") + "/"},
    )
    result = pipeline.run(entries)
    assert result == entries
    assert unrelated[1]["dst_fn"].endswith("metadata.csv")
    for _, entry in (entries[0], entries[2]):
        with rasterio.open(entry["dst_fn"]) as dst:
            np.testing.assert_array_equal(dst.read(), entry["expected"] + 1)
    assert entries[0][1]["dst_fn"] != entries[2][1]["dst_fn"]


def test_reject_non_raster_nested_hook(tmp_path):
    class BadRaster(AddRaster):
        meta_accepts = "point-stream"

    source = tmp_path / "sample.tif"
    make_file(source)
    with pytest.raises(TypeError, match="does not accept"):
        RasterPipeline(hooks=[BadRaster]).run([(None, {"dst_fn": str(source)})])


def test_invalid_stage():
    with pytest.raises(ValueError, match="stage"):
        RasterPipeline(stage="stream")
