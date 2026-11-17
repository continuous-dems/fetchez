"""Regression tests for Scratch ownership of focused catalog artifacts."""

import logging
from types import SimpleNamespace


from fetchez.core import (
    FetchContext,
    _run_grouped_stage,
    normalize_context,
    run_fetchez,
)
from fetchez.hooks import FetchHook
from fetchez.hooks.focus import FocusSink
from fetchez.modules.scratch import Scratch


class StubModule:
    """Source module with just enough interface for the Fetchez runner."""

    def __init__(self, name, results=None):
        self.name = name
        self.instance_id = name
        self.results = list(results or [])
        self.hooks = []
        self.context = None
        self.discovery_calls = 0
        self.fetch_calls = 0

    def run(self):
        self.discovery_calls += 1
        return self

    def fetch_entry(self, entry, **kwargs):
        self.fetch_calls += 1
        return 0


def bind(hook, context):
    hook.context = context
    return hook


def test_scratch_keeps_existing_manual_entry_interface():
    """The runtime role must not break Scratch's public data-injection role."""
    scratch = Scratch(
        url="file:///tmp/source.tif",
        path="source.tif",
        datatype="raster",
        use_cache=False,
    )
    scratch.run()
    assert len(scratch.results) == 1
    assert scratch.results[0]["url"] == "file:///tmp/source.tif"
    assert scratch.results[0]["data_type"] == "raster"


def test_ownerless_catalog_artifact_uses_scratch_even_with_one_active_module():
    source = StubModule("source-a")
    context = FetchContext()
    context.scratch = Scratch(use_cache=False)
    context.artifacts.publish("final-dem", "composite.tif")

    focused = bind(FocusSink(target="final-dem"), context).run(
        [(source, {"dst_fn": "source-a.tif", "status": 0})]
    )

    assert len(focused) == 1
    owner, entry = focused[0]
    assert owner is context.scratch
    assert owner is not source
    assert entry["dst_fn"] == "composite.tif"
    assert entry["artifacts"]["final-dem"] == "composite.tif"
    assert entry["artifact_owner"] is None
    assert context.artifacts.get("final-dem").owner is None


def test_known_catalog_producer_resolves_to_source_module():
    source = StubModule("source-a")
    context = FetchContext(plan=SimpleNamespace(modules_by_id={"source-a": source}))
    context.scratch = Scratch(use_cache=False)
    context.artifacts.publish("processed", "processed.tif", owner="source-a")

    # The producing source entry is no longer active.
    focused = bind(FocusSink(target="processed"), context).run([])

    assert len(focused) == 1
    assert focused[0][0] is source
    assert focused[0][1]["artifact_owner"] == "source-a"


def test_unknown_catalog_producer_uses_scratch_without_changing_provenance(caplog):
    context = FetchContext()
    context.scratch = Scratch(use_cache=False)
    artifact = context.artifacts.publish(
        "qc-report", "qc.json", owner="retired-producer", metadata={"kind": "qc"}
    )

    with caplog.at_level(logging.WARNING):
        focused = bind(FocusSink(target="qc-report"), context).run([])

    assert len(focused) == 1
    assert focused[0][0] is context.scratch
    assert focused[0][1]["artifact_owner"] == "retired-producer"
    assert context.artifacts.get("qc-report") is artifact
    assert artifact.owner == "retired-producer"
    assert artifact.metadata == {"kind": "qc"}
    assert "retired-producer" in caplog.text


def test_legacy_entry_artifact_preserves_its_module():
    source = StubModule("source-a")
    context = FetchContext()
    context.scratch = Scratch(use_cache=False)
    entry = {
        "dst_fn": "source-a.tif",
        "artifacts": {"processed": "legacy.tif"},
    }

    focused = bind(FocusSink(target="processed"), context).run([(source, entry)])

    assert len(focused) == 1
    assert focused[0][0] is source
    assert focused[0][1]["dst_fn"] == "legacy.tif"


def test_catalog_does_not_duplicate_a_legacy_artifact_path():
    source = StubModule("source-a")
    context = FetchContext()
    context.scratch = Scratch(use_cache=False)
    context.artifacts.publish("processed", "same.tif")
    entries = [
        (
            source,
            {
                "dst_fn": "input.tif",
                "artifacts": {"processed": "same.tif"},
            },
        )
    ]

    focused = bind(FocusSink(target="processed"), context).run(entries)

    assert len(focused) == 1
    assert focused[0][0] is source
    assert focused[0][1]["dst_fn"] == "same.tif"


def test_scratch_owner_passes_grouped_stage_validation():
    source = StubModule("source-a")
    context = FetchContext()
    context.scratch = Scratch(use_cache=False)
    synthetic_entry = {"dst_fn": "final.tif", "status": 0}

    # Core must recognize Scratch as an owner, without adding it to the
    # source discovery/acquisition list.
    result = _run_grouped_stage(
        "collection",
        [source],
        [],
        source_entries=[(context.scratch, synthetic_entry)],
        context=context,
    )

    assert result == [(context.scratch, synthetic_entry)]


class PublishComposite(FetchHook):
    name = "test-publish-composite"
    meta_stage = "collection"

    def run(self, entries):
        self.context.artifacts.publish("final-dem", "composite.tif")
        return entries


def test_direct_runner_creates_scratch_without_discovering_or_fetching_it(monkeypatch):
    """Verify the runtime owner exists even without a compiled recipe plan."""
    scratch_run_calls = []
    scratch_fetch_calls = []

    def forbidden_run(self):
        scratch_run_calls.append(self)
        raise AssertionError("runtime Scratch must not be discovered")

    def forbidden_fetch(self, entry, **kwargs):
        scratch_fetch_calls.append((self, entry))
        raise AssertionError("runtime Scratch must not fetch entries")

    monkeypatch.setattr(Scratch, "run", forbidden_run)
    monkeypatch.setattr(Scratch, "fetch_entry", forbidden_fetch)

    source = StubModule("source-a", [{"dst_fn": "input.tif", "status": 0}])
    context = FetchContext()
    hooks = [PublishComposite(), FocusSink(target="final-dem")]

    result = run_fetchez(
        [source], global_hooks=hooks, context=context, discover=False, threads=1
    )

    assert isinstance(context.scratch, Scratch)
    assert len(result) == 1
    assert result[0][0] is context.scratch
    assert result[0][1]["dst_fn"] == "composite.tif"
    assert scratch_run_calls == []
    assert scratch_fetch_calls == []
    assert source.fetch_calls == 1
    assert context.scratch.context is None
    assert all(hook.context is None for hook in hooks)
    assert source.context is None


def test_direct_runner_with_no_source_entries_can_focus_catalog_artifact():
    """Global collection hooks must run even when acquisition returns no entries."""
    context = FetchContext()
    result = run_fetchez(
        [],
        global_hooks=[PublishComposite(), FocusSink(target="final-dem")],
        context=context,
        discover=False,
        threads=1,
    )
    assert len(result) == 1
    assert result[0][0] is context.scratch
    assert result[0][1]["dst_fn"] == "composite.tif"


def test_each_execution_uses_a_distinct_runtime_scratch():
    contexts = [FetchContext(), FetchContext()]
    results = []
    for ctx in contexts:
        results.append(
            run_fetchez(
                [],
                global_hooks=[PublishComposite(), FocusSink(target="final-dem")],
                context=ctx,
                discover=False,
                threads=1,
            )
        )

    assert contexts[0].scratch is not contexts[1].scratch
    assert results[0][0][0] is contexts[0].scratch
    assert results[1][0][0] is contexts[1].scratch
    assert contexts[0].artifacts is not contexts[1].artifacts
    assert normalize_context(contexts[0]) is contexts[0]


def test_without_scratch_unresolvable_artifact_still_warns_and_passes_through(caplog):
    """Direct FocusSink calls outside a bound runner remain non-fatal."""
    context = FetchContext()
    source = StubModule("source-a")
    current = [(source, {"dst_fn": "existing.tif"})]
    context.artifacts.publish("final-dem", "unowned.tif")

    with caplog.at_level(logging.WARNING):
        result = bind(FocusSink(target="final-dem"), context).run(current)

    assert result is current
    assert "scratch" in caplog.text.lower() or "owner" in caplog.text.lower()
