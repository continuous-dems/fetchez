# tests/test_streams.py

from __future__ import annotations

from typing import Any

import pytest

from fetchez.streams.base import BaseStream


class ReaderError(Exception):
    """Stands in for an error a reader raises partway through a file."""


class DummyModule:
    """Minimal module implementation for exercising BaseStream."""

    def __init__(self, hooks: list[Any]):
        self.name = "dummy"
        self.hooks = hooks
        self.results = [
            {
                "url": "https://example.test/data.bin",
                "dst_fn": "data.bin",
            }
        ]

    def run(self):
        return self

    def fetch_entry(
        self,
        entry: dict[str, Any],
        check_size: bool = True,
        verbose: bool = True,
    ) -> int:
        return 0


class AttachStreamHook:
    """Attach a stream that yields ``chunks``, then raises ``error`` if given."""

    name = "attach-stream"
    stage = "file"

    def __init__(self, chunks: list[Any], error: Exception | None = None):
        self.chunks = chunks
        self.error = error

    def run(self, entries):
        def stream():
            yield from self.chunks
            if self.error is not None:
                raise self.error

        for _, entry in entries:
            entry["stream"] = stream()

        return entries

    def teardown(self):
        pass


def _stream(chunks, error=None, **kwargs):
    return BaseStream([DummyModule([AttachStreamHook(chunks, error)])], **kwargs)


def test_stream_yields_every_chunk():
    assert list(_stream([1, 2, 3])) == [1, 2, 3]


def test_reader_error_is_raised_after_the_chunks_read():
    """The reader's own exception reaches the caller, not an early end of the stream."""
    error = ReaderError("aux granule could not be fetched")
    seen = []

    with pytest.raises(ReaderError) as raised:
        for chunk in _stream([1, 2], error):
            seen.append(chunk)

    assert raised.value is error
    assert seen == [1, 2]


def test_reader_error_ends_the_stream_when_failures_are_ignored():
    assert list(_stream([1, 2], ReaderError("ignored"), ignore_failures=True)) == [1, 2]
