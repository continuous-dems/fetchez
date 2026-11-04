"""Explicit recipe labels reach manifest hooks via native contribution IDs."""

from fetchez.core import run_fetchez
from fetchez.entry import dataset_id, source_id
from test_core_lifecycle import DummyModule, RecordingHook


def test_instance_ids_distinguish_owners_without_changing_contributions():
    events = []
    original = {
        "url": "https://example.test/shared.bin",
        "dst_fn": "shared.bin",
        "contribution_id": {"classification": "bottom"},
    }
    modules = [DummyModule(events, results=[original]) for _ in range(2)]
    for module, label in zip(modules, ("target", "reference"), strict=True):
        module.instance_id_explicit = True
        module.instance_id = label

    class Inspect(RecordingHook):
        def run(self, entries):
            assert [mod.instance_id for mod, _ in entries] == [
                "target",
                "reference",
            ]

            assert all(
                entry["contribution_id"] == {"classification": "bottom"}
                for _, entry in entries
            )

            assert len({dataset_id(entry) for _, entry in entries}) == 1
            assert len({source_id(entry) for _, entry in entries}) == 1

            return entries

    run_fetchez(
        modules, threads=1, global_hooks=[Inspect("inspect", "manifest", events)]
    )
    assert original["contribution_id"] == {"classification": "bottom"}
    # assert "fetched" not in original


def test_unnamed_recipe_display_label_does_not_change_processed_identity():
    module = DummyModule([])
    module.instance_id_explicit = False
    module.instance_id = "entry_1"
    before = dataset_id(module.results[0])
    result = run_fetchez([module], threads=1)
    assert dataset_id(result[0][1]) == before
    assert "contribution_id" not in result[0][1]
