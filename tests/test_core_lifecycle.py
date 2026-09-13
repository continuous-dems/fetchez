# tests/test_core_lifecycle.py

from __future__ import annotations

from typing import Any

import pytest

from fetchez.core import run_fetchez


class DummyModule:
    """Minimal module implementation for exercising run_fetchez()."""

    def __init__(
        self,
        events: list[str],
        *,
        hooks: list[Any] | None = None,
        results: list[dict[str, Any]] | None = None,
        name: str = "dummy",
    ):
        self.name = name
        self.hooks = hooks or []
        self.results = results or [
            {
                "url": "https://example.test/data.bin",
                "dst_fn": "data.bin",
            }
        ]
        self.events = events

    def fetch_entry(
        self,
        entry: dict[str, Any],
        check_size: bool = True,
        verbose: bool = True,
    ) -> int:
        self.events.append("fetch")
        entry["fetched"] = True
        return 0


class RecordingHook:
    """Minimal hook that records execution and teardown."""

    def __init__(
        self,
        name: str,
        stage: str,
        events: list[str],
        *,
        fail: bool = False,
    ):
        self.name = name
        self.stage = stage
        self.events = events
        self.fail = fail

    def run(self, entries):
        self.events.append(self.name)

        if self.fail:
            raise RuntimeError(f"{self.name} failed")

        return entries

    def teardown(self):
        self.events.append(f"{self.name}:teardown")


class StreamProducerHook(RecordingHook):
    """Attach a lazy stream whose exhaustion is observable."""

    def __init__(self, events: list[str], name: str = "stream-producer"):
        super().__init__(name, "stream", events)

    def run(self, entries):
        self.events.append(self.name)

        def stream():
            self.events.append("stream:consume")
            yield {"value": 1}
            yield {"value": 2}

        for _, entry in entries:
            entry["stream"] = stream()

        return entries


class ExistingStreamHook(RecordingHook):
    """Attach a stream during the file stage."""

    def __init__(self, events: list[str]):
        super().__init__("existing-stream", "file", events)

    def run(self, entries):
        self.events.append(self.name)

        for _, entry in entries:
            entry["stream"] = iter([1, 2, 3])

        return entries


def test_run_fetchez_hook_lifecycle_order():
    events = []

    manifest = RecordingHook("manifest", "manifest", events)
    file_hook = RecordingHook("file", "file", events)
    stream_hook = StreamProducerHook(events)
    collection = RecordingHook("collection", "collection", events)

    module = DummyModule(
        events,
        hooks=[
            manifest,
            file_hook,
            stream_hook,
            collection,
        ],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events == [
        "manifest",
        "fetch",
        "file",
        "stream-producer",
        "stream:consume",
        # Current run_fetchez semantics:
        # teardown occurs when the executor exits, before collection hooks.
        "manifest:teardown",
        "file:teardown",
        "stream-producer:teardown",
        "collection:teardown",
        "collection",
    ]


def test_module_manifest_runs_before_global_manifest():
    events = []

    module_manifest = RecordingHook(
        "module-manifest",
        "manifest",
        events,
    )
    global_manifest = RecordingHook(
        "global-manifest",
        "manifest",
        events,
    )

    module = DummyModule(
        events,
        hooks=[module_manifest],
    )

    run_fetchez(
        [module],
        threads=1,
        global_hooks=[global_manifest],
        ignore_failures=False,
    )

    assert events.index("module-manifest") < events.index("global-manifest")
    assert events.index("global-manifest") < events.index("fetch")


def test_module_collection_runs_before_global_collection():
    events = []

    module_collection = RecordingHook(
        "module-collection",
        "collection",
        events,
    )
    global_collection = RecordingHook(
        "global-collection",
        "collection",
        events,
    )

    module = DummyModule(
        events,
        hooks=[module_collection],
    )

    run_fetchez(
        [module],
        threads=1,
        global_hooks=[global_collection],
        ignore_failures=False,
    )

    assert events.index("module-collection") < events.index("global-collection")


def test_stream_is_exhausted_before_collection():
    events = []

    stream_hook = StreamProducerHook(events)
    collection = RecordingHook(
        "collection",
        "collection",
        events,
    )

    module = DummyModule(
        events,
        hooks=[stream_hook, collection],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events.index("stream-producer") < events.index("stream:consume")
    assert events.index("stream:consume") < events.index("collection")


def test_stream_init_is_auto_injected_before_other_stream_hooks(monkeypatch):
    events = []

    class AutoStreamInit(RecordingHook):
        def __init__(self):
            super().__init__("stream-init", "stream", events)

        def run(self, entries):
            self.events.append(self.name)

            for _, entry in entries:
                entry["stream"] = iter([1])

            return entries

    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(
            lambda cls, name: AutoStreamInit if name == "stream-init" else None
        ),
    )

    transform = RecordingHook(
        "stream-transform",
        "stream",
        events,
    )

    module = DummyModule(
        events,
        hooks=[transform],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events.index("stream-init") < events.index("stream-transform")


@pytest.mark.parametrize("initializer_name", ["stream-init", "stream_data"])
def test_explicit_stream_initializer_prevents_auto_injection(
    monkeypatch,
    initializer_name,
):
    events = []
    auto_init_calls = 0

    class AutoStreamInit(RecordingHook):
        def __init__(self):
            nonlocal auto_init_calls
            auto_init_calls += 1
            super().__init__("stream-init", "stream", events)

    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(lambda cls, name: AutoStreamInit),
    )

    explicit_init = RecordingHook(
        initializer_name,
        "stream",
        events,
    )
    transform = RecordingHook(
        "transform",
        "stream",
        events,
    )

    module = DummyModule(
        events,
        hooks=[transform, explicit_init],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert auto_init_calls == 0
    assert events.count(initializer_name) == 1
    assert events.index(initializer_name) < events.index("transform")


def test_existing_stream_prevents_auto_initialization(monkeypatch):
    events = []
    auto_init_calls = 0

    class AutoStreamInit(RecordingHook):
        def __init__(self):
            nonlocal auto_init_calls
            auto_init_calls += 1
            super().__init__("stream-init", "stream", events)

    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(lambda cls, name: AutoStreamInit),
    )

    module = DummyModule(
        events,
        hooks=[
            ExistingStreamHook(events),
            RecordingHook("stream-transform", "stream", events),
        ],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert auto_init_calls == 0
    assert "stream-transform" in events


def test_auto_stream_init_failure_honors_ignore_failures_false(monkeypatch):
    events = []

    class FailingStreamInit(RecordingHook):
        def __init__(self):
            super().__init__(
                "stream-init",
                "stream",
                events,
                fail=True,
            )

    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(lambda cls, name: FailingStreamInit),
    )

    module = DummyModule(
        events,
        hooks=[
            RecordingHook(
                "stream-transform",
                "stream",
                events,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="stream-init"):
        run_fetchez(
            [module],
            threads=1,
            ignore_failures=False,
        )

    assert "stream-init" in events
    assert "stream-transform" not in events


def test_stream_hook_failure_marks_entry_failed_when_ignored():
    events = []

    failing = RecordingHook(
        "broken-stream-hook",
        "stream",
        events,
        fail=True,
    )

    # Existing stream prevents automatic stream-init from affecting this test.
    module = DummyModule(
        events,
        hooks=[
            ExistingStreamHook(events),
            failing,
        ],
    )

    results = run_fetchez(
        [module],
        threads=1,
        ignore_failures=True,
    )

    assert len(results) == 1

    _, entry = results[0]

    assert entry["status"] == "failed"
    assert "broken-stream-hook failed" in entry["error_message"]


def test_file_hook_failure_skips_stream_hooks():
    events = []

    file_hook = RecordingHook(
        "broken-file-hook",
        "file",
        events,
        fail=True,
    )
    stream_hook = RecordingHook(
        "stream-transform",
        "stream",
        events,
    )

    module = DummyModule(
        events,
        hooks=[file_hook, stream_hook],
    )

    results = run_fetchez(
        [module],
        threads=1,
        ignore_failures=True,
    )

    assert "broken-file-hook" in events
    assert "stream-transform" not in events

    _, entry = results[0]
    assert entry["status"] == "failed"


def test_configured_hook_teardown_once_across_multiple_entries():
    events = []

    hook = RecordingHook(
        "transform",
        "file",
        events,
    )

    module = DummyModule(
        events,
        hooks=[hook],
        results=[
            {"url": "one", "dst_fn": "one"},
            {"url": "two", "dst_fn": "two"},
            {"url": "three", "dst_fn": "three"},
        ],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events.count("transform") == 3
    assert events.count("transform:teardown") == 1


def test_hook_teardown_runs_exactly_once():
    events = []

    file_hook = RecordingHook(
        "file-hook",
        "file",
        events,
    )
    stream_hook = StreamProducerHook(
        events,
        name="stream-hook",
    )

    module = DummyModule(
        events,
        hooks=[file_hook, stream_hook],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events.count("file-hook:teardown") == 1
    assert events.count("stream-hook:teardown") == 1


def test_auto_injected_stream_init_is_torn_down(monkeypatch):
    events = []

    class AutoStreamInit(RecordingHook):
        def __init__(self):
            super().__init__(
                "stream-init",
                "stream",
                events,
            )

        def run(self, entries):
            self.events.append(self.name)

            for _, entry in entries:
                entry["stream"] = iter([1])

            return entries

    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(lambda cls, name: AutoStreamInit),
    )

    module = DummyModule(
        events,
        hooks=[
            RecordingHook(
                "stream-transform",
                "stream",
                events,
            )
        ],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert events.count("stream-init:teardown") == 1


class MixedStreamFileHook(RecordingHook):
    def __init__(self, events):
        super().__init__("fan-out", "file", events)

    def run(self, entries):
        self.events.append(self.name)

        owner, entry = entries[0]

        with_stream = dict(entry)
        with_stream["dst_fn"] = "with-stream"
        with_stream["stream"] = iter([1])

        without_stream = dict(entry)
        without_stream["dst_fn"] = "without-stream"
        without_stream.pop("stream", None)

        return [
            (owner, with_stream),
            (owner, without_stream),
        ]


def test_auto_stream_init_participates_in_hook_history(
    monkeypatch,
):
    events = []
    history = []

    class AutoStreamInit(RecordingHook):
        def __init__(self):
            super().__init__("stream-init", "stream", events)

        def run(self, entries):
            self.events.append(self.name)

            for _, entry in entries:
                entry["stream"] = iter([1])

            return entries

    from fetchez import core
    from fetchez.registry import HookRegistry

    monkeypatch.setattr(
        core.utils,
        "_log_hook_history",
        lambda entries, hook: history.append(hook.name),
    )

    monkeypatch.setattr(
        HookRegistry,
        "load_builtins",
        classmethod(lambda cls: None),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        classmethod(lambda cls, name: AutoStreamInit),
    )

    module = DummyModule(
        events,
        hooks=[
            RecordingHook(
                "stream-transform",
                "stream",
                events,
            )
        ],
    )

    run_fetchez(
        [module],
        threads=1,
        ignore_failures=False,
    )

    assert history == [
        "stream-init",
        "stream-transform",
    ]
