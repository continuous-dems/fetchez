"""Regression tests for lazy Recipe-backed fetchez.read streams."""

from types import SimpleNamespace

import pytest

from fetchez.api import read
from fetchez.recipe import Recipe
from fetchez.streams.base import BaseStream


def test_read_is_lazy_and_compiles_again_for_each_iteration(monkeypatch, tmp_path):
    from fetchez.registry import PresetRegistry

    monkeypatch.setattr(PresetRegistry, "load_all", lambda: None)
    monkeypatch.setattr(PresetRegistry, "get_preset", lambda name: None)
    calls = []

    class FakeModule:
        def run(self):
            calls.append("discover")

    class FakePlan:
        def __init__(self, config):
            self.config = config
            self.modules = [FakeModule()]
            self.global_hooks = []

        def execute(self):
            for module in self.modules:
                module.run()
            calls.append("execute")
            # Use the genuine QueueSinkHook interception contract.
            sink = self.global_hooks[-1]
            entries = [(self.modules[0], {"stream": iter([b"abc", b"def"])})]
            entries = sink.run(entries)
            assert list(entries[0][1]["stream"]) == [b"abc", b"def"]

    def compile_(self, context, *, ignore_failures=False):
        calls.append("compile")
        assert self.config["modules"] == ["example"]
        assert self.config["global_hooks"][0]["name"] == "stream-init"
        assert self.config["global_hooks"][0]["args"]["profile"] == "csv-default"
        return FakePlan(self.config)

    monkeypatch.setattr(Recipe, "compile", compile_)
    # A profile hook need not be imported/registered until iteration.
    stream = read("example").pipe("stream-init", profile="csv-default")
    assert isinstance(stream, BaseStream)
    assert calls == []
    assert list(stream) == [b"abc", b"def"]
    assert list(stream) == [b"abc", b"def"]
    assert calls == ["compile", "discover", "execute"] * 2


def test_read_preserves_local_shorthand_and_dict_options(monkeypatch, tmp_path):
    source = tmp_path / "survey.xyz"
    source.write_text("0 0 2\n", encoding="utf-8")

    def compile_(self, context, *, ignore_failures=False):
        # `read` must not reinterpret source names; Recipe.compile owns
        # local_fs normalization, name precedence, presets and hooks.
        assert self.config["modules"] == [
            str(source),
            {"module": str(source), "args": {"ext": ".xyz"}},
        ]
        assert self.config["global_hooks"] == []
        return SimpleNamespace(modules=[], global_hooks=[], execute=lambda: None)

    monkeypatch.setattr(Recipe, "compile", compile_)
    stream = read([str(source), {"module": str(source), "args": {"ext": ".xyz"}}])
    assert list(stream) == []


def test_read_propagates_stream_errors(monkeypatch):
    class FakePlan:
        modules = []
        global_hooks = []

        def execute(self):
            raise ValueError("reader failed")

    monkeypatch.setattr(Recipe, "compile", lambda self, context, **kw: FakePlan())
    with pytest.raises(ValueError, match="reader failed"):
        list(read("example"))
