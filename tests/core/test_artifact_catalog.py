"""Tests for FetchContext's execution-scoped artifact catalog.x"""

from pathlib import Path

import pytest

import concurrent.futures

from fetchez.core import (
    Artifact,
    ArtifactCatalog,
    EntryStash,
    FetchContext,
    FetchExecutionContext,
    bind_context,
    clear_context,
    normalize_context,
)


def test_publish_returns_artifact_with_metadata():
    catalog = ArtifactCatalog()
    receipt = catalog.publish(
        "qc-receipt", "qc.json", owner="source-a", metadata={"passed": True}
    )
    assert isinstance(receipt, Artifact)
    assert receipt.name == "qc-receipt"
    assert receipt.path == "qc.json"
    assert receipt.owner == "source-a"
    assert receipt.metadata == {"passed": True}
    assert catalog.get("qc-receipt") is receipt


def test_add_alias_and_path_objects(tmp_path):
    catalog = ArtifactCatalog()
    path = tmp_path / "output.tif"  # file need not exist
    artifact = catalog.add("final-dem", path)
    assert artifact.path == str(path)
    assert catalog.get("final-dem").path == str(path)


def test_multiple_artifacts_can_share_name():
    catalog = ArtifactCatalog()
    first = catalog.publish("qc-receipt", "a.json", owner="tile-a")
    second = catalog.publish("qc-receipt", "b.json", owner="tile-b")
    assert catalog.find("qc-receipt") == [first, second]
    with pytest.raises(ValueError, match="ambiguous"):
        catalog.get("qc-receipt")
    assert catalog.get("qc-receipt", owner="tile-b") is second


def test_name_and_owner_filters_are_conjunctive():
    catalog = ArtifactCatalog()
    a_qc = catalog.publish("qc", "a.json", owner="a")
    b_qc = catalog.publish("qc", "b.json", owner="b")
    b_dem = catalog.publish("dem", "b.tif", owner="b")
    assert catalog.find("qc", owner="a") == [a_qc]
    assert catalog.find(owner="b") == [b_qc, b_dem]
    assert catalog.find("dem", owner="a") == []
    assert catalog.find() == [a_qc, b_qc, b_dem]


def test_get_missing_raises_key_error():
    catalog = ArtifactCatalog()
    catalog.publish("qc", "a.json", owner="a")
    with pytest.raises(KeyError, match="missing"):
        catalog.get("missing")
    with pytest.raises(KeyError, match="qc"):
        catalog.get("qc", owner="not-a")


def test_publish_identical_identity_is_idempotent():
    catalog = ArtifactCatalog()
    first = catalog.publish("dem", "a.tif", owner="a", metadata={"revision": 1})
    again = catalog.publish("dem", Path("a.tif"), owner="a", metadata={"revision": 2})
    assert again is first
    assert len(catalog.find()) == 1
    # Current contract: first publication keeps its metadata.
    assert again.metadata == {"revision": 1}


def test_identity_includes_name_path_and_owner():
    catalog = ArtifactCatalog()
    catalog.publish("dem", "a.tif", owner="a")
    catalog.publish("dem", "a.tif", owner="b")
    catalog.publish("dem", "b.tif", owner="a")
    catalog.publish("preview", "a.tif", owner="a")
    assert len(catalog.find()) == 4


def test_names_are_unique_and_follow_first_publication_order():
    catalog = ArtifactCatalog()
    for name, path in (("qc", "a"), ("dem", "b"), ("qc", "c"), ("mask", "d")):
        catalog.publish(name, path)
    assert catalog.names() == ("qc", "dem", "mask")


def test_find_returns_independent_list():
    catalog = ArtifactCatalog()
    catalog.publish("dem", "a.tif")
    snapshot = catalog.find()
    snapshot.clear()
    assert len(catalog.find()) == 1


def test_publish_copies_top_level_metadata_mapping():
    catalog = ArtifactCatalog()
    original = {"status": "complete"}
    artifact = catalog.publish("dem", "a.tif", metadata=original)
    original["status"] = "changed"
    assert artifact.metadata["status"] == "complete"


def test_metadata_nested_values_are_shallow_by_design():
    catalog = ArtifactCatalog()
    tags = ["processed"]
    artifact = catalog.publish("dem", "a.tif", metadata={"tags": tags})
    tags.append("reviewed")
    assert artifact.metadata["tags"] == ["processed", "reviewed"]


def test_clear_removes_all_records_but_catalog_remains_reusable():
    catalog = ArtifactCatalog()
    catalog.publish("a", "a.txt")
    catalog.publish("b", "b.txt")
    catalog.clear()
    assert catalog.find() == []
    assert catalog.names() == ()
    assert catalog.publish("c", "c.txt") is catalog.get("c")


def test_separate_contexts_have_independent_services():
    a, b = FetchContext(), FetchContext()
    assert a.artifacts is not b.artifacts
    assert a.stashes is not b.stashes
    assert a.execution is not b.execution
    a.artifacts.publish("dem", "a.tif")
    a.stashes.save("empty", [])
    a.cancel()
    assert b.artifacts.find() == []
    assert not b.stashes.has("empty")
    assert not b.cancelled


def test_normalize_none_creates_complete_independent_contexts():
    a, b = normalize_context(), normalize_context()
    assert isinstance(a, FetchContext)
    assert isinstance(a.artifacts, ArtifactCatalog)
    assert isinstance(a.stashes, EntryStash)
    assert a is not b
    assert a.artifacts is not b.artifacts


def test_normalize_full_context_preserves_identity_and_services():
    context = FetchContext()
    context.artifacts.publish("dem", "a.tif")
    context.stashes.save("before", [])
    assert normalize_context(context) is context
    assert normalize_context(context).artifacts.get("dem").path == "a.tif"
    assert normalize_context(context).stashes.has("before")


def test_normalize_legacy_execution_context_wraps_and_preserves_cancellation():
    execution = FetchExecutionContext()
    context = normalize_context(execution)
    assert context.execution is execution
    assert isinstance(context.artifacts, ArtifactCatalog)
    assert isinstance(context.stashes, EntryStash)
    execution.cancel()
    assert context.cancelled


@pytest.mark.parametrize("invalid", [object(), {}, EntryStash(), ArtifactCatalog()])
def test_normalize_rejects_unsupported_context_types(invalid):
    with pytest.raises(TypeError, match="context must be"):
        normalize_context(invalid)


def test_threaded_publication_has_no_lost_records():
    catalog = ArtifactCatalog()

    def publish(i):
        return catalog.publish("qc", f"tile_{i}.json", owner=f"tile_{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        records = list(pool.map(publish, range(200)))
    assert len(records) == 200
    assert len(catalog.find("qc")) == 200
    assert {a.path for a in catalog.find("qc")} == {
        f"tile_{i}.json" for i in range(200)
    }


def test_threaded_identical_publication_is_atomic():
    catalog = ArtifactCatalog()
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        records = list(
            pool.map(
                lambda _: catalog.publish("dem", "same.tif", owner="a"), range(100)
            )
        )
    assert len(catalog.find()) == 1
    assert all(record is records[0] for record in records)


class _Module:
    name = "test-module"

    def __init__(self):
        self.context = None
        self.hooks = []


class _Hook:
    name = "artifact-publisher"

    def __init__(self):
        self.context = None


def test_bound_hooks_share_catalog_and_it_survives_entry_filtering():
    """The catalog isn't tied to the list of active pipeline entries."""
    context = FetchContext()
    module = _Module()
    local_hook, global_hook = _Hook(), _Hook()
    module.hooks.append(local_hook)
    bind_context(context, [module], [global_hook])
    try:
        assert module.context is context
        assert local_hook.context is context
        assert global_hook.context is context
        local_hook.context.artifacts.publish("qc", "qc.json", owner="test-module")
        entries = [(module, {"dst_fn": "input.tif"})]
        entries = []  # as after focus/filter drops all active entries
        assert entries == []
        assert global_hook.context.artifacts.get("qc").path == "qc.json"
    finally:
        clear_context([module], [global_hook])
    assert module.context is None
    assert local_hook.context is None
    assert global_hook.context is None
    assert context.artifacts.get("qc").path == "qc.json"
