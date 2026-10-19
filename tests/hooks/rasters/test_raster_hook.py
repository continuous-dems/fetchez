"""Standalone tests for the thin raster hook base.

In a Fetchez checkout, import RasterHook from fetchez.hooks.raster instead.
"""

import numpy as np
import pytest

from fetchez.hooks.rasters.base import RasterHook


@pytest.fixture(scope="module")
def base_hook():
    yield RasterHook


# @pytest.fixture(scope="module")
# def base_hook():
#     fetchez = types.ModuleType("fetchez")
#     fetchez.__path__ = []
#     hooks = types.ModuleType("fetchez.hooks")
#     hooks.__path__ = []

#     class FetchHook:
#         def __init__(self, **kwargs):
#             pass

#     hooks.FetchHook = FetchHook
#     names = {"fetchez": fetchez, "fetchez.hooks": hooks}
#     previous = {key: sys.modules.get(key) for key in names}
#     sys.modules.update(names)
#     try:
#         spec = importlib.util.spec_from_file_location("fetchez.hooks.raster", "/mnt/data/raster_hook.py")
#         module = importlib.util.module_from_spec(spec)
#         sys.modules[spec.name] = module
#         spec.loader.exec_module(module)
#         yield module.RasterHook
#     finally:
#         sys.modules.pop("fetchez.hooks.raster", None)
#         for key, original in previous.items():
#             if original is None:
#                 sys.modules.pop(key, None)
#             else:
#                 sys.modules[key] = original


def test_chained_hooks_use_previous_results(base_hook):
    class AddOne(base_hook):
        name = "add-one"

        def process_chunk(self, chunk, entry):
            return {**chunk, "data": chunk["data"] + 1}

    class TimesTwo(base_hook):
        name = "times-two"

        def process_chunk(self, chunk, entry):
            return {**chunk, "data": chunk["data"] * 2}

    metadata = object()
    original = np.array([[1, 2]], dtype=np.float32)
    entry = {
        "stream": iter([{"context": metadata, "data": original}]),
        "stream_type": "raster-stream",
    }
    entries = TimesTwo().run(AddOne().run([(None, entry)]))
    result = list(entries[0][1]["stream"])
    np.testing.assert_array_equal(result[0]["data"], [[4, 6]])
    np.testing.assert_array_equal(original, [[1, 2]])
    assert result[0]["context"] is metadata


def test_lazy_and_multiple_entries(base_hook):
    calls = []

    class Record(base_hook):
        name = "record"

        def process_chunk(self, chunk, entry):
            calls.append(entry["name"])
            return chunk

    entries = [
        (
            None,
            {
                "name": str(i),
                "stream": iter([{"data": i}]),
                "stream_type": "raster-stream",
            },
        )
        for i in range(2)
    ]
    result = Record().run(entries)
    assert calls == []
    assert list(result[1][1]["stream"])[0]["data"] == 1
    assert list(result[0][1]["stream"])[0]["data"] == 0
    assert calls == ["1", "0"]


def test_skip_no_stream(base_hook):
    class Noop(base_hook):
        name = "noop"

        def process_chunk(self, chunk, entry):
            return chunk

    entry = {"dst_fn": "test.tif"}
    assert Noop().run([(None, entry)])[0][1] is entry


def test_reject_wrong_stream_type(base_hook):
    class Noop(base_hook):
        name = "noop"

        def process_chunk(self, chunk, entry):
            return chunk

    with pytest.raises(TypeError, match="expected raster-stream"):
        Noop().run([(None, {"stream": iter([]), "stream_type": "point-stream"})])


def test_drop_and_invalid_return(base_hook):
    class Drop(base_hook):
        name = "drop"

        def process_chunk(self, chunk, entry):
            return None if chunk["data"] == 0 else chunk

    entry = {"stream_type": "raster-stream", "stream": iter([{"data": 0}, {"data": 1}])}
    assert [c["data"] for c in Drop().run([(None, entry)])[0][1]["stream"]] == [1]

    class Invalid(base_hook):
        name = "invalid"

        def process_chunk(self, chunk, entry):
            return 12

    entry = {"stream_type": "raster-stream", "stream": iter([{"data": 1}])}
    with pytest.raises(TypeError, match="chunk dict"):
        list(Invalid().run([(None, entry)])[0][1]["stream"])
