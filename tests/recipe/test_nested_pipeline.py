"""Nested PipelinePlan execution contracts; merge into tests/test_nested_pipeline.py."""

from pathlib import Path
import pytest
from fetchez.core import FetchContext, HookExecutionError
from fetchez.hooks import FetchHook
from fetchez.recipe import PipelinePlan


class LocalSource:
    """Minimal, network-free provider exercising the real core lifecycle."""

    name = "nested-test-source"

    def __init__(self, path):
        self.path = Path(path)
        self.hooks = []
        self.results = []
        self.context = None
        self.discovery_count = 0
        self.fetch_count = 0

    def run(self):
        assert self.context is not None
        self.discovery_count += 1
        self.results = [
            {"url": self.path.as_uri(), "dst_fn": str(self.path), "data_type": "text"}
        ]
        return self

    def fetch_entry(self, entry, *, check_size=True, verbose=True):
        self.fetch_count += 1
        assert entry["url"] == self.path.as_uri()
        assert Path(entry["dst_fn"]).is_file()
        return 0


class ChildCollector(FetchHook):
    name = "nested-test-child-collector"
    meta_stage = "collection"

    def __init__(self, observed):
        super().__init__()
        self.observed = observed

    def run(self, entries):
        self.observed["child_context"] = self.context
        self.context.stashes.save("same-key", entries)
        self.context.artifacts.publish("dem", "reference.tif")
        return entries


class InvokeChild(FetchHook):
    name = "nested-test-invoke-child"
    meta_stage = "collection"

    def __init__(self, child_plan, observed):
        super().__init__()
        self.child_plan = child_plan
        self.observed = observed

    def run(self, entries):
        parent = self.context
        parent.stashes.save("same-key", entries)
        parent.artifacts.publish("parent-output", "parent.tif")
        child_context = parent.child(plan=self.child_plan)
        child_outputs = self.child_plan.execute(context=child_context)
        assert self.context is parent  # parent binding must survive nested run
        assert not parent.cancelled
        self.observed.update(
            parent=parent, child=child_context, child_outputs=child_outputs
        )
        return entries


class FailingChild(FetchHook):
    name = "nested-test-failing-child"
    meta_stage = "collection"

    def run(self, entries):
        raise ValueError("expected child failure")


class CatchChildFailure(FetchHook):
    name = "nested-test-catch-failure"
    meta_stage = "collection"

    def __init__(self, child_plan, observed):
        super().__init__()
        self.child_plan = child_plan
        self.observed = observed

    def run(self, entries):
        parent = self.context
        child = parent.child(plan=self.child_plan)
        with pytest.raises(HookExecutionError, match="expected child failure"):
            self.child_plan.execute(context=child)
        assert not parent.cancelled
        assert self.context is parent
        self.observed["caught"] = True
        return entries


def plan(modules=(), hooks=()):
    return PipelinePlan(
        config={"execution": {"threads": 1}},
        modules=list(modules),
        global_hooks=list(hooks),
    )


def test_nested_plan_discovers_and_runs_without_mutating_parent(tmp_path):
    parent_path = tmp_path / "parent.txt"
    child_path = tmp_path / "child.txt"
    parent_path.write_text("parent")
    child_path.write_text("child")
    parent_source, child_source = LocalSource(parent_path), LocalSource(child_path)
    observed = {}
    child_hook = ChildCollector(observed)
    child_plan = plan([child_source], [child_hook])
    parent_hook = InvokeChild(child_plan, observed)
    parent_plan = plan([parent_source], [parent_hook])

    parent_outputs = parent_plan.execute()

    assert parent_source.discovery_count == parent_source.fetch_count == 1
    assert child_source.discovery_count == child_source.fetch_count == 1
    assert [entry["dst_fn"] for _, entry in parent_outputs] == [str(parent_path)]
    assert [entry["dst_fn"] for _, entry in observed["child_outputs"]] == [
        str(child_path)
    ]

    parent, child = observed["parent"], observed["child"]
    assert child is observed["child_context"]
    assert child.parent is parent
    assert parent.plan is parent_plan
    assert child.plan is child_plan
    assert parent.stashes.get("same-key")[0][1]["dst_fn"] == str(parent_path)
    assert child.stashes.get("same-key")[0][1]["dst_fn"] == str(child_path)
    assert parent.artifacts.names() == ("parent-output",)
    assert child.artifacts.names() == ("dem",)
    assert parent.scratch is not child.scratch
    assert parent_source.context is child_source.context is None
    assert parent_hook.context is child_hook.context is None
    assert parent.scratch.context is child.scratch.context is None


def test_child_failure_can_be_caught_without_cancelling_parent(tmp_path):
    path = tmp_path / "parent.txt"
    path.write_text("parent")
    observed = {}
    hook = CatchChildFailure(plan(hooks=[FailingChild()]), observed)
    outputs = plan([LocalSource(path)], [hook]).execute()
    assert len(outputs) == 1
    assert observed["caught"]


def test_supplied_context_with_wrong_plan_is_rejected():
    """Expected to fail until PipelinePlan.execute validates context.plan."""
    first, second = plan(), plan()
    with pytest.raises(ValueError, match="plan|context"):
        first.execute(context=FetchContext(plan=second))


def test_child_and_sibling_cancellation_are_independent():
    parent = FetchContext()
    child, sibling = parent.child(), parent.child()
    child.cancel()
    assert child.cancelled
    assert not sibling.cancelled
    assert not parent.cancelled
    parent.cancel()
    assert sibling.cancelled
