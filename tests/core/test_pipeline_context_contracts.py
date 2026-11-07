"""Regression contracts for the Fetchez instance-ID and execution-context refactor.

All tests are offline. They exercise the real run_fetchez() rather than mocking
away discovery, context binding, or hook execution.
"""

from copy import deepcopy

import pytest

from fetchez.core import (
    FetchCancelled,
    FetchExecutionContext,
    normalize_context,
    run_fetchez,
)
from fetchez.entry import dataset_id, entry_id, source_id
from fetchez.recipe import PipelinePlan


class StubModule:
    """Minimal executor-compatible module; no external registry or I/O."""

    name = "contract-source"

    def __init__(self, *, instance_id=None, entries=None, hooks=(), fail=None):
        self.instance_id = instance_id
        self.results = deepcopy(entries if entries is not None else [])
        self.hooks = list(hooks)
        self.context = None
        self._discovery_failed = False
        self.fail = fail
        self.run_calls = 0
        self.fetch_calls = 0
        self.discovery_context = None

    def run(self):
        self.run_calls += 1
        self.discovery_context = self.context
        if self.fail:
            raise self.fail
        return self

    def fetch_entry(self, entry, check_size=True, verbose=True):
        self.fetch_calls += 1
        assert self.context is not None
        assert check_size is True
        entry["fetched"] = True
        return 0


class ObserveHook:
    name = "observer"
    stage = "manifest"

    def __init__(self):
        self.context = None
        self.seen_context = None
        self.seen_entries = None
        self.teardown_context = None
        self.teardown_calls = 0

    def run(self, entries):
        self.seen_context = self.context
        self.seen_entries = list(entries)
        return entries

    def teardown(self):
        self.teardown_calls += 1
        self.teardown_context = self.context


def _sample_entry():
    return {
        "url": "https://example.invalid/dem.bin",
        "dst_fn": "dem.bin",
        "contribution_id": {"classification": "ground"},
    }


def test_context_normalization_keeps_legacy_cancellation_controller():
    execution = FetchExecutionContext()
    context = normalize_context(execution)
    assert context.execution is execution
    assert context.plan is None
    assert normalize_context(context) is context
    assert not context.cancelled
    context.cancel()
    assert context.cancelled and execution.cancelled


def test_context_normalization_rejects_unrelated_values():
    with pytest.raises(TypeError, match="context"):
        normalize_context({"plan": "not a context"})


def test_direct_execution_creates_context_without_a_plan():
    module = StubModule(entries=[_sample_entry()])
    hook = ObserveHook()
    results = run_fetchez([module], global_hooks=[hook], threads=1, discover=True)
    assert module.run_calls == 1
    assert module.discovery_context is hook.seen_context
    assert hook.seen_context.plan is None
    assert module.fetch_calls == 1
    assert results[0][0] is module
    assert results[0][1]["fetched"] is True
    assert module.context is None and hook.context is None


def test_plan_is_shared_by_discovery_manifest_and_lookup():
    local = ObserveHook()
    global_hook = ObserveHook()
    a = StubModule(instance_id="bottom", entries=[_sample_entry()], hooks=[local])
    b = StubModule(instance_id="reference", entries=[_sample_entry()])
    plan = PipelinePlan(
        config={"execution": {"threads": 1}}, modules=[a, b], global_hooks=[global_hook]
    )
    results = plan.execute()
    assert len(results) == 2
    assert plan.modules_by_id == {"bottom": a, "reference": b}
    assert a.discovery_context is b.discovery_context
    assert local.seen_context is global_hook.seen_context is a.discovery_context
    assert global_hook.seen_context.plan is plan
    assert global_hook.seen_context.plan.modules_by_id["bottom"] is a
    assert [owner.instance_id for owner, _ in global_hook.seen_entries] == [
        "bottom",
        "reference",
    ]
    assert all(item.context is None for item in (a, b, local, global_hook))


def test_named_occurrences_do_not_modify_any_entry_id():
    entry = _sample_entry()
    before = (source_id(entry), entry_id(entry), dataset_id(entry))
    a = StubModule(instance_id="view_a", entries=[entry])
    b = StubModule(instance_id="view_b", entries=[entry])
    hook = ObserveHook()
    run_fetchez([a, b], threads=1, global_hooks=[hook])
    assert len(hook.seen_entries) == 2
    for owner, observed in hook.seen_entries:
        assert owner.instance_id in {"view_a", "view_b"}
        assert observed["contribution_id"] == entry["contribution_id"]
        assert (source_id(observed), entry_id(observed), dataset_id(observed)) == before


def test_discover_false_never_invokes_run_and_fetches_existing_results():
    module = StubModule(
        entries=[_sample_entry()], fail=AssertionError("must not discover")
    )
    results = run_fetchez([module], discover=False, threads=1)
    assert module.run_calls == 0
    assert module.fetch_calls == 1
    assert results[0][1]["fetched"] is True
    assert module.context is None


def test_discovery_exception_strict_cleans_all_contexts():
    hook = ObserveHook()
    module = StubModule(hooks=[hook], fail=RuntimeError("lookup failed"))
    with pytest.raises(RuntimeError, match="lookup failed"):
        run_fetchez([module], global_hooks=[ObserveHook()], threads=1, discover=True)
    assert module.run_calls == 1
    assert module.context is None and hook.context is None
    assert module.results == []


def test_discovery_exception_tolerant_preserves_partial_results():
    bad = StubModule(
        entries=[_sample_entry()],
        fail=RuntimeError("API offline"),
    )
    good = StubModule(entries=[_sample_entry()])

    results = run_fetchez(
        [bad, good],
        ignore_failures=True,
        threads=1,
        discover=True,
    )

    # Discovery attempted for both modules.
    assert bad.run_calls == good.run_calls == 1

    # The executor does not modify module discovery state.
    assert bad._discovery_failed is False
    assert len(bad.results) == 1

    # Tolerant execution continues with available entries.
    assert bad.fetch_calls == 1
    assert good.fetch_calls == 1

    assert [owner for owner, _ in results] == [bad, good]

    # Transient execution context is cleaned up.
    assert bad.context is good.context is None


def test_discovery_failed_flag_does_not_discard_partial_results():
    class PartialDiscoveryModule(StubModule):
        def run(self):
            super().run()
            self._discovery_failed = True
            return self

    module = PartialDiscoveryModule(entries=[_sample_entry()])

    results = run_fetchez(
        [module],
        discover=True,
        threads=1,
    )

    assert module._discovery_failed is True
    assert module.fetch_calls == 1
    assert len(results) == 1
    assert results[0][0] is module


def test_partial_discovery_results_are_preserved():
    class SoftFailure(StubModule):
        def run(self):
            super().run()
            self._discovery_failed = True
            return self

    module = SoftFailure(entries=[_sample_entry()])

    results = run_fetchez([module], discover=True, threads=1)

    assert module._discovery_failed is True
    assert len(results) == 1
    assert module.fetch_calls == 1
    assert results[0][1]["fetched"] is True
    assert module.context is None


def test_pre_cancelled_context_does_not_discover_and_is_unbound():
    module = StubModule(entries=[_sample_entry()])
    execution = FetchExecutionContext()
    execution.cancel()
    with pytest.raises(FetchCancelled):
        run_fetchez([module], context=execution)
    assert module.run_calls == 0
    assert module.context is None


def test_manifest_hook_failure_cleans_context_and_runs_teardown():
    class FailingHook(ObserveHook):
        def run(self, entries):
            self.seen_context = self.context
            raise ValueError("bad manifest")

    hook = FailingHook()
    module = StubModule(entries=[_sample_entry()])
    with pytest.raises(RuntimeError, match="manifest-hook"):
        run_fetchez([module], global_hooks=[hook], threads=1)
    assert hook.teardown_calls == 1
    assert hook.teardown_context is hook.seen_context
    assert module.context is hook.context is None


def test_no_results_still_unbinds_all_initial_hooks():
    local = ObserveHook()
    global_hook = ObserveHook()
    module = StubModule(hooks=[local])
    assert run_fetchez([module], global_hooks=[global_hook]) == []
    assert module.context is local.context is global_hook.context is None


def test_plan_uses_current_instance_ids_without_mutating_modules():
    a = StubModule(instance_id="a")
    b = StubModule(instance_id="b")
    plan = PipelinePlan(config={}, modules=[a, b], global_hooks=[])
    assert plan.modules_by_id == {"a": a, "b": b}
    assert not hasattr(a, "_instance_ids")
    assert not hasattr(a, "_recipe_providers")
    assert a.context is b.context is None


def test_run_fetchez_default_uses_prepared_results():
    module = StubModule()
    module.results = [{"url": "https://example.test/file.dat"}]

    run_fetchez([module])

    assert module.run_calls == 0
    assert module.fetch_calls == 1
