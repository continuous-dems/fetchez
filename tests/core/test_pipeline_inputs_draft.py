"""Regression tests for prepared entry injection into Fetchez child pipelines."""

from pathlib import Path

import pytest

from fetchez.core import FetchContext, PipelineResult, run_fetchez
from fetchez.entry import entry_copy, entry_id, source_id
from fetchez.hooks import FetchHook
from fetchez.recipe import PipelinePlan


class LocalSource:
    """Small network-free source; no module registry or HTTP required."""

    name = "test-local-source"

    def __init__(self, path, hooks=()):
        self.path = Path(path)
        self.hooks = list(hooks)
        self.context = None
        self.results = []
        self.discover_calls = 0
        self.fetch_calls = 0

    def run(self):
        assert self.context is not None
        self.discover_calls += 1
        self.results = [make_entry(self.path)]
        return self

    def fetch_entry(self, entry, *, check_size=True, verbose=True):
        self.fetch_calls += 1
        assert Path(entry["dst_fn"]).is_file()
        entry["status"] = 0
        return 0


class RecordHook(FetchHook):
    name = "test-record-hook"

    def __init__(self, stage, events, *, mutate=False):
        super().__init__()
        self.stage = stage
        self.events = events
        self.mutate = mutate
        self.teardowns = 0

    def run(self, entries):
        assert self.context is not None
        self.events.append(
            (self.stage, self.context, [e["dst_fn"] for _, e in entries])
        )
        if self.mutate:
            for _, entry in entries:
                entry.setdefault("metadata", {}).setdefault("nested", {})["weight"] = 2
                entry.setdefault("artifacts", {})["child"] = "child-output.tif"
        return entries

    def teardown(self):
        self.teardowns += 1


class FailIfCalled(FetchHook):
    name = "test-parent-hook-must-not-run"
    meta_stage = "file"

    def run(self, entries):
        raise AssertionError("Parent local hook was re-executed in child")


def make_entry(path, *, url="https://example.invalid/original.tif"):
    return {
        "url": url,
        "dst_fn": str(path),
        "data_type": "tif",
        "status": 0,
        "metadata": {"nested": {"weight": 1}, "labels": ["original"]},
        "artifacts": {"source": str(path)},
    }


def plan(modules=(), hooks=(), *, discover_only=False):
    return PipelinePlan(
        config={"execution": {"threads": 1, "discover_only": discover_only}},
        modules=list(modules),
        global_hooks=list(hooks),
    )


def test_entry_copy_preserves_identity_and_isolates_nested_values(tmp_path):
    path = tmp_path / "parent.tif"
    path.write_bytes(b"raster")
    original = make_entry(path)
    clone = entry_copy(original)

    assert clone == original and clone is not original
    assert source_id(clone) == source_id(original)
    assert entry_id(clone) == entry_id(original)
    clone["metadata"]["nested"]["weight"] = 99
    clone["metadata"]["labels"].append("child")
    clone["artifacts"]["source"] = "changed.tif"
    assert original["metadata"]["nested"]["weight"] == 1
    assert original["metadata"]["labels"] == ["original"]
    assert original["artifacts"]["source"] == str(path)


def test_entry_copy_rejects_active_stream(tmp_path):
    entry = make_entry(tmp_path / "input.tif")
    entry["stream"] = iter([1, 2])
    with pytest.raises(ValueError, match="stream"):
        entry_copy(entry)


def test_prepared_only_pipeline_skips_parent_discovery_and_fetch(tmp_path):
    path = tmp_path / "input.tif"
    path.write_bytes(b"materialized")
    owner = LocalSource(path, hooks=[FailIfCalled()])
    original = make_entry(path)
    events = []
    hooks = [RecordHook(stage, events) for stage in ("file", "collection", "finalize")]

    parent_context = FetchContext()
    result = parent_context.execute(plan(hooks=hooks), inputs=[(owner, original)])

    assert isinstance(result, PipelineResult)
    assert result.context.parent is parent_context
    assert len(result.entries) == 1
    child_owner, child_entry = result.entries[0]
    assert child_owner is result.context.scratch
    assert child_owner is not owner
    assert owner.discover_calls == owner.fetch_calls == 0
    assert child_entry["url"] == original["url"]
    assert child_entry["metadata"] == original["metadata"]
    assert [stage for stage, _, _ in events] == ["file", "collection", "finalize"]
    assert all(ctx is result.context for _, ctx, _ in events)
    assert all(hook.context is None for hook in hooks)
    assert result.context.scratch.context is None
    assert not parent_context.cancelled


def test_injected_entry_changes_do_not_mutate_parent(tmp_path):
    path = tmp_path / "input.tif"
    path.write_bytes(b"data")
    original = make_entry(path)
    events = []
    child = plan(hooks=[RecordHook("file", events, mutate=True)])

    result = FetchContext().execute(child, inputs=[(LocalSource(path), original)])
    copied = result.entries[0][1]
    assert copied["metadata"]["nested"]["weight"] == 2
    assert copied["artifacts"]["child"] == "child-output.tif"
    assert original["metadata"]["nested"]["weight"] == 1
    assert "child" not in original["artifacts"]


def test_mixed_prepared_and_discovered_entries(tmp_path):
    prepared_path = tmp_path / "prepared.tif"
    discovered_path = tmp_path / "discovered.tif"
    prepared_path.write_bytes(b"prepared")
    discovered_path.write_bytes(b"discovered")
    original_owner = LocalSource(prepared_path)
    child_source = LocalSource(discovered_path)
    events = []

    result = FetchContext().execute(
        plan(modules=[child_source], hooks=[RecordHook("collection", events)]),
        inputs=[(original_owner, make_entry(prepared_path))],
    )
    actual = {entry["dst_fn"] for _, entry in result.entries}
    assert actual == {str(prepared_path), str(discovered_path)}
    assert child_source.discover_calls == child_source.fetch_calls == 1
    assert original_owner.discover_calls == original_owner.fetch_calls == 0
    assert len(events) == 1
    assert set(events[0][2]) == actual


def test_prepared_missing_file_raises_and_parent_survives(tmp_path):
    missing = tmp_path / "missing.tif"
    owner = LocalSource(missing)
    parent = FetchContext()
    with pytest.raises(FileNotFoundError, match="Prepared input does not exist"):
        parent.execute(plan(), inputs=[(owner, make_entry(missing))])
    assert not parent.cancelled
    assert owner.discover_calls == owner.fetch_calls == 0


def test_direct_plan_and_run_fetchez_accept_inputs(tmp_path):
    path = tmp_path / "input.tif"
    path.write_bytes(b"data")
    owner = LocalSource(path)
    supplied = [(owner, make_entry(path))]

    via_plan = plan().execute(inputs=supplied)
    via_runner = run_fetchez([], inputs=supplied)
    assert [item[1]["dst_fn"] for item in via_plan] == [str(path)]
    assert [item[1]["dst_fn"] for item in via_runner] == [str(path)]
    assert owner.fetch_calls == owner.discover_calls == 0


def test_empty_inputs_keep_empty_pipeline_behavior():
    assert plan().execute(inputs=[]) == []


def test_discover_only_keeps_existing_manifest_only_semantics(tmp_path):
    """Current contract: injected inputs start at file stage, not manifest."""
    path = tmp_path / "input.tif"
    path.write_bytes(b"data")
    events = []
    result = FetchContext().execute(
        plan(hooks=[RecordHook("manifest", events)], discover_only=True),
        inputs=[(LocalSource(path), make_entry(path))],
    )
    assert result.entries == []
    assert len(events) == 1
    assert events[0][0] == "manifest"
    assert events[0][2] == []
