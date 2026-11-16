"""Regression tests for execution-scoped entry stashes.

The tests use the current (module, entry) API; no network access is needed.
"""

import logging

import pytest

from fetchez.core import EntryStash, FetchContext, normalize_context, run_fetchez
from fetchez.hooks.focus import FocusSink, RestoreEntries, StashEntries


def pairs(*names):
    """Produce distinct owners and entries without requiring FetchModule setup."""
    return [
        (object(), {"url": f"file:///{name}.tif", "dst_fn": f"{name}.tif", "status": 0})
        for name in names
    ]


def bind(hook, context):
    hook.context = context
    return hook


def test_stash_round_trip_preserves_owners_and_values():
    original = pairs("a", "b")
    stash = EntryStash()
    stash.save("before", original)

    restored = stash.get("before")
    assert restored == original
    assert all(a is b for (a, _), (b, _) in zip(restored, original, strict=True))
    assert restored is not original
    assert all(a is not b for (_, a), (_, b) in zip(restored, original, strict=True))
    assert stash.has("before")
    assert stash.keys() == ("before",)


def test_snapshot_protects_top_level_fields_on_both_sides():
    original = pairs("a")
    stash = EntryStash()
    stash.save("checkpoint", original)

    original[0][1]["dst_fn"] = "changed.tif"
    first = stash.get("checkpoint")
    assert first[0][1]["dst_fn"] == "a.tif"
    first[0][1]["dst_fn"] = "modified-restoration.tif"
    assert stash.get("checkpoint")[0][1]["dst_fn"] == "a.tif"


def test_nested_values_and_live_objects_remain_shared_by_design():
    original = pairs("a")
    stream = iter([1, 2])
    original[0][1].update(metadata={"tags": ["initial"]}, stream=stream)
    stash = EntryStash()
    stash.save("checkpoint", original)

    restored = stash.get("checkpoint")
    assert restored[0][1]["stream"] is stream
    assert restored[0][1]["metadata"] is original[0][1]["metadata"]
    original[0][1]["metadata"]["tags"].append("changed")
    assert restored[0][1]["metadata"]["tags"] == ["initial", "changed"]


def test_empty_stash_is_distinguishable_from_missing_stash():
    stash = EntryStash()
    stash.save("empty", [])
    assert stash.has("empty")
    assert stash.get("empty") == []
    assert not stash.has("missing")
    with pytest.raises(KeyError, match="missing"):
        stash.get("missing")


def test_multiple_keys_and_overwrite():
    stash = EntryStash()
    stash.save("first", pairs("a"))
    stash.save("second", pairs("b"))
    stash.save("first", pairs("c"))
    assert [entry["dst_fn"] for _, entry in stash.get("first")] == ["c.tif"]
    assert [entry["dst_fn"] for _, entry in stash.get("second")] == ["b.tif"]
    assert stash.keys() == ("first", "second")


def test_fetch_contexts_do_not_share_stashes():
    a, b = FetchContext(), FetchContext()
    a.stashes.save("original", pairs("a"))
    assert a.stashes is not b.stashes
    assert not b.stashes.has("original")
    assert normalize_context(a) is a


def test_stash_and_restore_after_focus_removes_first_owner():
    context = FetchContext()
    initial = pairs("a", "b")
    initial[1][1]["artifacts"] = {"final-dem": "b-final.tif"}

    stashed = bind(StashEntries(key="original"), context).run(initial)
    focused = bind(FocusSink(target="final-dem"), context).run(stashed)
    assert len(focused) == 1
    assert focused[0][0] is initial[1][0]
    assert focused[0][1]["dst_fn"] == "b-final.tif"
    assert all(owner is not initial[0][0] for owner, _ in focused)

    restored = bind(RestoreEntries(key="original"), context).run(focused)
    assert [entry["dst_fn"] for _, entry in restored] == ["a.tif", "b.tif"]
    assert restored[0][0] is initial[0][0]
    assert restored[1][0] is initial[1][0]


@pytest.mark.parametrize("merge", [True, "true", "YES", "1"])
def test_restore_merge_appends_saved_entries(merge):
    context = FetchContext()
    original = pairs("a", "b")
    current = pairs("c")
    bind(StashEntries(key="before"), context).run(original)
    merged = bind(RestoreEntries(key="before", merge=merge), context).run(current)
    assert [entry["dst_fn"] for _, entry in merged] == ["c.tif", "a.tif", "b.tif"]
    assert [entry["dst_fn"] for _, entry in current] == ["c.tif"]


def test_restore_missing_stash_warns_and_passes_original(caplog):
    context = FetchContext()
    current = pairs("a")
    with caplog.at_level(logging.WARNING):
        result = bind(RestoreEntries(key="absent"), context).run(current)
    assert result is current
    assert "absent" in caplog.text


def test_hooks_can_save_and_restore_empty_pipeline():
    context = FetchContext()
    bind(StashEntries(key="empty"), context).run([])
    result = bind(RestoreEntries(key="empty"), context).run(pairs("a"))
    assert result == []


def test_stash_can_be_used_across_supported_stages():
    for stage in ("manifest", "collection", "finalize"):
        context = FetchContext()
        save = bind(StashEntries(key=stage, stage=stage), context)
        restore = bind(RestoreEntries(key=stage, stage=stage), context)
        save.run(pairs("a"))
        assert restore.run([])[0][1]["dst_fn"] == "a.tif"


class StubModule:
    """Minimal module to exercise the actual runner without downloading files."""

    name = "stash-test-module"

    def __init__(self, name, entries):
        self.name = name
        self.instance_id = name
        self.results = entries
        self.hooks = []
        self.context = None

    def fetch_entry(self, entry, **kwargs):
        return 0


def test_runner_binds_shared_context_and_clears_it_after_execution():
    """Integration test: collection stash -> focus -> restore, one real run_fetchez call."""
    module_a = StubModule("module-a", [{"dst_fn": "a.tif", "status": 0}])
    module_b = StubModule(
        "module-b",
        [{"dst_fn": "b.tif", "status": 0, "artifacts": {"final-dem": "b-final.tif"}}],
    )
    context = FetchContext()
    hooks = [
        StashEntries(key="before"),
        FocusSink(target="final-dem"),
        RestoreEntries(key="before"),
    ]

    result = run_fetchez(
        [module_a, module_b],
        global_hooks=hooks,
        context=context,
        threads=1,
        discover=False,
    )

    assert [entry["dst_fn"] for _, entry in result] == ["a.tif", "b.tif"]
    assert context.stashes.has("before")
    assert all(hook.context is None for hook in hooks)
    assert module_a.context is None and module_b.context is None
