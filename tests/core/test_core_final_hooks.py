"""Finished-output companions use the ordinary collection pipeline."""

from types import SimpleNamespace

import pytest

from fetchez.core import prepare_final_hooks, run_fetchez
from fetchez.hooks import FetchHook
from test_core_lifecycle import DummyModule, RecordingHook


class Publisher(FetchHook):
    name = "test-publisher"
    meta_stage = "collection"

    def __init__(self, events):
        super().__init__()
        self.events = events

    def run(self, entries):
        self.events.append("publish:" + entries[0][1]["dst_fn"])
        return entries


class Requester(RecordingHook):
    def final_hooks(self):
        return (Publisher(self.events),)


@pytest.mark.parametrize("scope", ["module", "global"])
def test_final_hook_sees_finished_outputs_after_collection(scope):
    events = []
    request = Requester("request", "collection", events)

    class Crop(RecordingHook):
        def run(self, entries):
            self.events.append("crop")
            return [(entries[0][0], dict(dst_fn="cropped.tif"))]

    crop = Crop("crop", "collection", events)
    module = DummyModule(events, hooks=[request] if scope == "module" else [])
    global_hooks = [crop] if scope == "module" else [request, crop]
    result = run_fetchez([module], global_hooks=global_hooks)
    assert (
        events.index("request")
        < events.index("crop")
        < events.index("publish:cropped.tif")
    )
    assert result[0][1]["dst_fn"] == "cropped.tif"
    assert not any(isinstance(h, Publisher) for h in global_hooks)


def test_explicit_publisher_overrides_automatic_configuration():
    events = []
    request = Requester("request", "collection", events)
    explicit = Publisher(events)
    hooks = [request, explicit]
    assert prepare_final_hooks([], hooks) == hooks


def test_preparation_is_idempotent_and_same_requester_only_runs_once():
    events = []
    request = Requester("request", "collection", events)
    modules = [SimpleNamespace(hooks=[request])]
    prepared = prepare_final_hooks(modules, [request])
    assert len(prepared) == 2
    assert prepare_final_hooks(modules, prepared) == prepared


def test_separate_requesters_keep_separate_publications():
    first = Requester("one", "collection", [])
    second = Requester("two", "collection", [])
    prepared = prepare_final_hooks([], [first, second])
    assert len(prepared) == 4
    assert prepare_final_hooks([], prepared) == prepared


def test_failed_processing_does_not_publish():
    events = []
    request = Requester("request", "collection", events)
    failure = RecordingHook("failed-crop", "collection", events, fail=True)
    with pytest.raises(RuntimeError, match="failed-crop"):
        run_fetchez([DummyModule(events)], global_hooks=[request, failure])
    assert not any(event.startswith("publish:") for event in events)


def test_final_hooks_must_be_collection_hooks():
    class Bad(Requester):
        def final_hooks(self):
            return (FetchHook(stage="stream"),)

    with pytest.raises(ValueError, match="configured collection hooks"):
        prepare_final_hooks([], [Bad("bad", "collection", [])])
