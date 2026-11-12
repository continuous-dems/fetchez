"""Offline tests for Fetchez discover-only execution."""

from dataclasses import dataclass, field

import pytest

from fetchez.core import FetchCancelled, FetchContext, run_fetchez


@dataclass(eq=False)
class Module:
    name: str = "example"
    results: list = field(default_factory=list)
    hooks: list = field(default_factory=list)
    discover_calls: int = 0
    fetch_calls: int = 0

    def run(self):
        self.discover_calls += 1
        self.results = [{"dst_fn": "demo.tif", "data_type": "raster"}]
        return self

    def fetch_entry(self, entry, **kwargs):
        self.fetch_calls += 1
        return 0


class Hook:
    def __init__(self, stage, callback=None):
        self.stage = stage
        self.name = f"test-{stage}"
        self.callback = callback
        self.calls = 0

    def run(self, entries):
        self.calls += 1
        if self.callback:
            return self.callback(entries)
        return entries

    def teardown(self):
        pass


def test_discover_only_skips_acquisition_and_collection():
    mod = Module()
    manifest = Hook("manifest")
    file_hook = Hook("file")
    stream_hook = Hook("stream")
    collection = Hook("collection")
    finalize = Hook("finalize")

    result = run_fetchez(
        [mod],
        discover=True,
        discover_only=True,
        global_hooks=[
            manifest,
            file_hook,
            stream_hook,
            collection,
            finalize,
        ],
    )

    assert mod.discover_calls == 1
    assert mod.fetch_calls == 0
    assert manifest.calls == 1
    assert file_hook.calls == 0
    assert stream_hook.calls == 0
    assert collection.calls == 0
    assert finalize.calls == 1
    assert len(result) == 1
    assert result[0][0] is mod


def test_discover_only_finalizes_filtered_manifest():
    mod = Module(
        results=[
            {"dst_fn": "a.tif", "data_type": "raster"},
            {"dst_fn": "b.laz", "data_type": "pointcloud"},
        ]
    )
    observed = []

    def filter_rasters(entries):
        return [
            (owner, item) for owner, item in entries if item["data_type"] == "raster"
        ]

    def record(entries):
        observed.extend(entries)
        return entries

    result = run_fetchez(
        [mod],
        discover_only=True,
        global_hooks=[
            Hook("manifest", filter_rasters),
            Hook("finalize", record),
        ],
    )

    assert mod.discover_calls == 0
    assert mod.fetch_calls == 0
    assert len(result) == len(observed) == 1
    assert result[0][1]["dst_fn"] == "a.tif"


def test_discover_only_finalizes_empty_manifest():
    mod = Module(results=[])
    observed = []

    def report(entries):
        observed.append(list(entries))
        return entries

    result = run_fetchez(
        [mod],
        discover_only=True,
        global_hooks=[Hook("finalize", report)],
    )

    assert result == []
    assert observed == [[]]
    assert mod.fetch_calls == 0


def test_discover_only_respects_cancellation():
    mod = Module(results=[{"dst_fn": "a.tif"}])
    context = FetchContext()
    finalize = Hook("finalize")

    def cancel(entries):
        context.cancel()
        return entries

    with pytest.raises(FetchCancelled):
        run_fetchez(
            [mod],
            discover_only=True,
            ignore_failures=True,
            context=context,
            global_hooks=[
                Hook("manifest", cancel),
                finalize,
            ],
        )

    assert finalize.calls == 0
    assert mod.fetch_calls == 0
    assert mod.context is None
