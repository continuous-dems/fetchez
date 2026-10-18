"""Standalone integration tests for RasterPipeline using real Rasterio I/O."""

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).parent


@pytest.fixture
def components():
    names = {}
    for key in (
        "fetchez",
        "fetchez.hooks",
        "fetchez.hooks.rasters",
        "fetchez.utils",
        "fetchez.registry",
        "fetchez.streams",
        "fetchez.streams.readers",
        "fetchez.streams.readers.base",
    ):
        mod = types.ModuleType(key)
        mod.__path__ = []
        names[key] = mod

    class FetchHook:
        meta_stage = "stream"

        def __init__(self, stage=None, **kwargs):
            self.stage = stage or self.meta_stage

        def teardown(self):
            pass

    class BaseReader:
        def __init__(self, path, region=None, **kwargs):
            self.region = region

        def yield_chunks(self):
            yield from self._read_chunks()

    names["fetchez.hooks"].FetchHook = FetchHook
    names["fetchez.streams.readers.base"].BaseReader = BaseReader
    names["fetchez.utils"].str2bool = bool

    class Registry:
        classes = {}

        @classmethod
        def get_class(cls, name):
            return cls.classes.get(name)

    names["fetchez.registry"].HookRegistry = Registry
    saved = {k: sys.modules.get(k) for k in names}
    sys.modules.update(names)
    loaded = []

    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        loaded.append(name)
        spec.loader.exec_module(module)
        return module

    try:
        _reader = load("fetchez.streams.readers.raster", "raster.py").RasterReader
        base = load("fetchez.hooks.raster", "raster_hook.py").RasterHook
        _writer = load(
            "fetchez.hooks.rasters.raster_writer", "raster_writer.py"
        ).RasterWrite
        pipe = load(
            "fetchez.hooks.rasters.raster_pipeline", "raster_pipeline.py"
        ).RasterPipeline

        class Add(base):
            name = "add"

            def __init__(self, amount=1, **kwargs):
                super().__init__(**kwargs)
                self.amount = amount

            def process_chunk(self, chunk, entry):
                return {**chunk, "data": chunk["data"] + self.amount}

        Registry.classes["add"] = Add
        yield pipe, Add
    finally:
        for k in loaded:
            sys.modules.pop(k, None)
        for k, old in saved.items():
            if old is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = old


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
    ) as ds:
        ds.write(data)
        ds.update_tags(dataset="composite-test")
        for band in range(1, 4):
            ds.set_band_description(band, f"band_{band}")
            ds.set_band_unit(band, "m")
    return data


@pytest.mark.parametrize("stage", ["file", "collection"])
def test_stage_multiband_and_chained_hooks(components, tmp_path, stage):
    Pipeline, Add = components
    source = tmp_path / "source.tif"
    original = make_file(source)
    entry = {"dst_fn": str(source), "data_type": "raster"}
    pipeline = Pipeline(
        stage=stage,
        reader={"chunk_size": 3, "buffer": 1},
        hooks=[{"name": "add", "args": {"amount": 3}}, Add(amount=7)],
        writer={"suffix": "_filtered"},
    )
    assert pipeline.stage == stage
    rows = pipeline.run([(object(), entry)])
    assert rows[0][1] is entry
    assert "stream" not in entry
    assert entry["dst_fn"].endswith("source_filtered.tif")
    with rasterio.open(entry["dst_fn"]) as out:
        np.testing.assert_array_equal(out.read(), original + 10)
        assert out.descriptions == ("band_1", "band_2", "band_3")
        assert out.tags()["dataset"] == "composite-test"
    with rasterio.open(source) as original_ds:
        np.testing.assert_array_equal(original_ds.read(), original)


def test_many_entries_and_skipping_unrelated(components, tmp_path):
    Pipeline, _ = components
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
    pipe = Pipeline(
        hooks=["add"],
        reader={"chunk_size": "full"},
        writer={"output_path": str(tmp_path / "processed") + "/"},
    )
    result = pipe.run(entries)
    assert result == entries
    assert unrelated[1]["dst_fn"].endswith("metadata.csv")
    for _, entry in (entries[0], entries[2]):
        with rasterio.open(entry["dst_fn"]) as ds:
            np.testing.assert_array_equal(ds.read(), entry["expected"] + 1)
    assert entries[0][1]["dst_fn"] != entries[2][1]["dst_fn"]


def test_reject_non_raster_nested_hook(components, tmp_path):
    Pipeline, Add = components

    class Bad(Add):
        meta_accepts = "point-stream"

    source = tmp_path / "sample.tif"
    make_file(source)
    with pytest.raises(TypeError, match="does not accept"):
        Pipeline(hooks=[Bad]).run([(None, {"dst_fn": str(source)})])


def test_invalid_stage(components):
    Pipeline, _ = components
    with pytest.raises(ValueError):
        Pipeline(stage="stream")
