"""Offline contract tests for the Fetchez finalize hook stage.

Place alongside test_core_lifecycle_resilience.py in tests/core/. No network needed.
"""

from dataclasses import dataclass, field

import pytest

import fetchez.core as core


@dataclass(eq=False)
class Module:
    name: str
    results: list = field(default_factory=list)
    hooks: list = field(default_factory=list)
    fetch_status: object = 0

    def fetch_entry(self, entry, check_size=True, verbose=True):
        if isinstance(self.fetch_status, BaseException):
            raise self.fetch_status
        return self.fetch_status


class Hook:
    def __init__(self, stage, name, events, *, func=None, fail=False):
        self.stage = stage
        self.name = name
        self.events = events
        self.func = func
        self.fail = fail
        self.runs = 0
        self.teardowns = 0

    def run(self, entries):
        self.runs += 1
        self.events.append(f"run:{self.name}")
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return self.func(entries) if self.func else entries

    def teardown(self):
        self.teardowns += 1
        self.events.append(f"teardown:{self.name}")


def entry(label):
    return {"url": f"https://example.invalid/{label}", "dst_fn": f"{label}.tif"}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(core.utils, "_log_hook_history", lambda *a, **kw: None)
    monkeypatch.setattr(
        core.utils, "merge_hooks", lambda local, global_: [*local, *global_]
    )


def execute(modules, global_hooks=(), **kwargs):
    return core.run_fetchez(
        modules, global_hooks=list(global_hooks), threads=1, **kwargs
    )


def test_finalize_runs_after_collection_even_when_declared_first():
    events = []
    mod = Module("source", [entry("a")])
    finalize = Hook("finalize", "report", events)
    collection = Hook("collection", "process", events)

    execute([mod], [finalize, collection])

    assert events == [
        "run:process",
        "teardown:process",
        "run:report",
        "teardown:report",
    ]
    assert finalize.runs == finalize.teardowns == 1


def test_finalize_sees_replaced_final_entry_and_artifacts():
    events = []
    mod = Module("source", [entry("raw-a"), entry("raw-b")])
    final = {
        "dst_fn": "final_dem.tif",
        "artifacts": {"multi_stack": "stack.tif", "provenance": "provenance.tif"},
    }
    observed = []

    def produce(entries):
        assert len(entries) == 2
        return [(mod, final)]

    def inspect(entries):
        observed.extend(entries)
        assert entries == [(mod, final)]
        assert entries[0][1]["artifacts"]["provenance"] == "provenance.tif"
        return entries

    result = execute(
        [mod],
        [
            Hook("finalize", "report", events, func=inspect),
            Hook("collection", "create-dem", events, func=produce),
        ],
    )

    assert result == observed == [(mod, final)]
    assert events.index("run:create-dem") < events.index("run:report")


def test_module_local_finalize_scopes_entries_and_global_sees_updated_result():
    events = []
    a = Module("a", [entry("a")])
    b = Module("b", [entry("b")])
    seen = []

    def local(entries):
        seen.append(("local", [owner.name for owner, _ in entries]))
        for _, item in entries:
            item["local_qc"] = True
        return entries

    def global_report(entries):
        seen.append(("global", [owner.name for owner, _ in entries]))
        assert next(item for owner, item in entries if owner is a)["local_qc"]
        return entries

    a.hooks.append(Hook("finalize", "local-a", events, func=local))
    execute([a, b], [Hook("finalize", "global", events, func=global_report)])

    assert seen[0] == ("local", ["a"])
    assert sorted(seen[1][1]) == ["a", "b"]
    assert events.index("run:local-a") < events.index("run:global")


# @pytest.mark.xfail(strict=True, reason="module-local finalize currently moves its entries to the end")
def test_module_local_finalize_preserves_interleaved_entry_order():
    """Regression: replacing module entries should not move them to the end."""
    events = []
    a = Module("a", [entry("a")])
    b = Module("b", [entry("b")])

    # A global collection hook can interleave ownership arbitrarily.
    def interleave(entries):
        return [(a, a.results[0]), (b, b.results[0])]

    a.hooks.append(Hook("finalize", "local-a", events))
    result = execute([a, b], [Hook("collection", "reorder", events, func=interleave)])
    assert [owner.name for owner, _ in result] == ["a", "b"]


def test_multiple_global_finalizers_run_in_order_and_pass_changes():
    events = []
    mod = Module("a", [entry("a")])

    def add_report(entries):
        entries[0][1].setdefault("artifacts", {})["report"] = "qc.html"
        return entries

    def check_report(entries):
        assert entries[0][1]["artifacts"]["report"] == "qc.html"
        return entries

    execute(
        [mod],
        [
            Hook("finalize", "write-report", events, func=add_report),
            Hook("finalize", "publish", events, func=check_report),
        ],
    )
    assert [event for event in events if event.startswith("run:")] == [
        "run:write-report",
        "run:publish",
    ]


def test_strict_collection_failure_skips_finalize_and_tears_down_collection():
    events = []
    mod = Module("a", [entry("a")])
    collection = Hook("collection", "bad-collection", events, fail=True)
    finalizer = Hook("finalize", "report", events)

    with pytest.raises(RuntimeError, match="bad-collection"):
        execute([mod], [collection, finalizer])

    assert finalizer.runs == 0
    assert collection.teardowns == 1


@pytest.mark.parametrize("local", [False, True], ids=["global", "module-local"])
def test_strict_finalize_failure_tears_down_after_run(local):
    events = []
    mod = Module("a", [entry("a")])
    failing = Hook("finalize", "bad-finalize", events, fail=True)
    if local:
        mod.hooks.append(failing)
        configured = []
    else:
        configured = [failing]

    with pytest.raises(RuntimeError, match="bad-finalize"):
        execute([mod], configured)

    assert events == ["run:bad-finalize", "teardown:bad-finalize"]


@pytest.mark.parametrize("local", [False, True], ids=["global", "module-local"])
def test_permissive_finalize_failure_continues_to_next_hook(local):
    events = []
    mod = Module("a", [entry("a")])
    bad = Hook("finalize", "bad-finalize", events, fail=True)
    next_hook = Hook("finalize", "after-failure", events)
    if local:
        mod.hooks.extend([bad, next_hook])
        configured = []
    else:
        configured = [bad, next_hook]

    result = execute([mod], configured, ignore_failures=True)

    assert len(result) == 1
    assert bad.runs == next_hook.runs == 1
    assert bad.teardowns == next_hook.teardowns == 1


# @pytest.mark.xfail(strict=True, reason="collection currently wraps FetchCancelled in RuntimeError")
def test_cancellation_during_collection_skips_finalize():
    events = []
    mod = Module("a", [entry("a")])
    finalizer = Hook("finalize", "report", events)

    def cancel(entries):
        raise core.FetchCancelled("cancelled during collection")

    with pytest.raises(core.FetchCancelled) as _exc:
        execute([mod], [Hook("collection", "cancel", events, func=cancel), finalizer])
    assert finalizer.runs == 0


def test_cancellation_between_collection_and_finalize_skips_finalize():
    events = []
    mod = Module("a", [entry("a")])
    ctx = core.FetchContext()

    def cancel(entries):
        ctx.cancel()
        return entries

    finalizer = Hook("finalize", "report", events)
    with pytest.raises(core.FetchCancelled) as _exc:
        execute(
            [mod],
            [Hook("collection", "cancel", events, func=cancel), finalizer],
            context=ctx,
        )

    assert finalizer.runs == 0
    assert finalizer.teardowns == 1
    assert ctx.cancelled


def test_finalize_not_torn_down_before_run():
    events = []
    mod = Module("a", [entry("a")])
    hook = Hook("finalize", "finalize", events)
    execute([mod], [hook])
    assert events == ["run:finalize", "teardown:finalize"]


def test_no_entries_skips_finalize_as_current_contract():
    events = []
    mod = Module("empty", [])
    hook = Hook("finalize", "report", events)
    assert execute([mod], [hook]) == []
    assert hook.runs == 0
