"""Offline contract/regression tests for Fetchez's execution lifecycle."""

from dataclasses import dataclass, field

import pytest

import fetchez.core as core


@dataclass(eq=False)
class FakeModule:
    name: str = "fake"
    results: list = field(default_factory=list)
    hooks: list = field(default_factory=list)
    fetch_status: object = 0
    calls: int = 0

    def fetch_entry(self, entry, check_size=True, verbose=True):
        self.calls += 1
        if isinstance(self.fetch_status, BaseException):
            raise self.fetch_status
        return self.fetch_status


class FakeHook:
    def __init__(self, stage, *, name="fake-hook", fail=False, response=None):
        self.stage = stage
        self.name = name
        self.fail = fail
        self.response = response
        self.runs = 0
        self.teardowns = 0

    def run(self, entries):
        self.runs += 1
        if self.fail:
            raise RuntimeError(f"{self.stage} exploded")
        return entries if self.response is None else self.response

    def teardown(self):
        self.teardowns += 1


@pytest.fixture(autouse=True)
def isolated_execution(monkeypatch):
    """Avoid actual fetching, progress rendering and hook-history side effects."""
    # core.STOP_EVENT.clear()
    monkeypatch.setattr(core.utils, "_log_hook_history", lambda *a, **kw: None)
    monkeypatch.setattr(
        core.utils, "merge_hooks", lambda local, global_: [*local, *global_]
    )
    yield
    # core.STOP_EVENT.clear()


def entry(label="item"):
    return {"dst_fn": f"{label}.bin", "url": f"https://example.invalid/{label}"}


@pytest.mark.parametrize(
    "failure", [5, IOError("network down")], ids=["status", "exception"]
)
def test_download_failure_strict_raises(failure):
    mod = FakeModule(results=[entry()], fetch_status=failure)
    with pytest.raises(RuntimeError, match="Failed to fetch"):
        core.run_fetchez([mod], threads=1, ignore_failures=False)
    assert mod.calls == 1


@pytest.mark.parametrize(
    "failure", [-1, IOError("network down")], ids=["status", "exception"]
)
def test_download_failure_tolerant_marks_entry_and_returns_it(failure):
    mod = FakeModule(results=[entry()], fetch_status=failure)
    result = core.run_fetchez([mod], threads=1, ignore_failures=True)
    assert len(result) == 1
    assert result[0][1]["status"] == "failed"
    assert result[0][1]["error_message"]


@pytest.mark.parametrize("stage", ["manifest", "file", "stream", "collection"])
def test_failing_hook_strict_raises(stage):
    hook = FakeHook(
        stage, name="stream-init" if stage == "stream" else "fake-hook", fail=True
    )
    mod = FakeModule(results=[entry()], hooks=[hook])
    with pytest.raises(RuntimeError, match=stage):
        core.run_fetchez([mod], threads=1, ignore_failures=False)


@pytest.mark.parametrize("stage", ["file", "stream"])
def test_entry_hook_failure_tolerant_marks_failed_and_stops_entry(stage):
    bad = FakeHook(
        stage, name="stream-init" if stage == "stream" else "fake-hook", fail=True
    )
    after = FakeHook(stage, name="should-not-run")
    mod = FakeModule(results=[entry()], hooks=[bad, after])
    result = core.run_fetchez([mod], threads=1, ignore_failures=True)
    assert result[0][1]["status"] == "failed"
    assert result[0][1]["error_message"]
    assert after.runs == 0


def test_successful_entry_preserved():
    mod = FakeModule(results=[entry()])
    result = core.run_fetchez([mod], threads=1, ignore_failures=False)
    assert result == [(mod, mod.results[0])]
    assert mod.calls == 1


def test_shared_hook_torn_down_once_on_success():
    shared = FakeHook("file")
    a = FakeModule(name="a", results=[entry("a")], hooks=[shared])
    b = FakeModule(name="b", results=[entry("b")], hooks=[shared])
    core.run_fetchez([a, b], threads=1, global_hooks=[shared], ignore_failures=False)
    assert shared.teardowns == 1


def test_malformed_manifest_entry_fails_strict_mode():
    mod = FakeModule(results=["not-an-entry"])
    with pytest.raises(
        (TypeError, ValueError, RuntimeError), match="entry|dict|malformed"
    ):
        core.run_fetchez([mod], threads=1, ignore_failures=False)


# @pytest.mark.xfail(strict=True, reason="run_fetchez default is tolerant although API and Recipe default to strict")
def test_run_fetchez_defaults_to_strict_failure_policy():
    mod = FakeModule(results=[entry()], fetch_status=-1)
    with pytest.raises(RuntimeError, match="Failed to fetch"):
        core.run_fetchez([mod], threads=1)


def test_empty_manifest_returns_empty_collection():
    mod = FakeModule(results=[])
    assert core.run_fetchez([mod], threads=1, ignore_failures=False) == []


def test_collection_failure_still_tears_down_only_after_hook_runs():
    events = []

    class FailingCollection(FakeHook):
        def run(self, entries):
            events.append("run")
            raise RuntimeError("collection failed")

        def teardown(self):
            events.append("teardown")

    hook = FailingCollection("collection")
    mod = FakeModule(results=[entry()], hooks=[hook])
    with pytest.raises(RuntimeError, match="collection"):
        core.run_fetchez([mod], threads=1, ignore_failures=False)
    assert events == ["run", "teardown"]


def test_collection_hook_runs_before_teardown():
    events = []

    class CollectionHook(FakeHook):
        def run(self, entries):
            events.append("run")
            return entries

        def teardown(self):
            events.append("teardown")

    hook = CollectionHook("collection")
    mod = FakeModule(results=[entry()], hooks=[hook])

    core.run_fetchez([mod], threads=1, ignore_failures=False)

    assert events == ["run", "teardown"]


def test_manifest_failure_still_tears_down_hooks():
    events = []

    class ManifestHook(FakeHook):
        def run(self, entries):
            events.append("run")
            raise RuntimeError("manifest failed")

        def teardown(self):
            events.append("teardown")

    hook = ManifestHook("manifest")
    mod = FakeModule(results=[entry()], hooks=[hook])

    with pytest.raises(RuntimeError, match="manifest failed"):
        core.run_fetchez([mod], threads=1, ignore_failures=False)

    assert events == ["run", "teardown"]


@pytest.mark.parametrize("fail", [False, True])
def test_empty_or_invalid_manifest_clears_execution_context(fail):
    module = FakeModule(results=["invalid"] if fail else [])

    if fail:
        with pytest.raises(ValueError):
            core.run_fetchez([module], threads=1)
    else:
        assert core.run_fetchez([module], threads=1) == []

    assert module._execution_context is None
