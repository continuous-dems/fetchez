"""Offline regression tests for fetchez.core.Fetch and its transfer helpers."""

from __future__ import annotations

import ftplib
import io
from pathlib import Path
from unittest.mock import Mock
import logging
from types import SimpleNamespace

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from lxml import etree
import threading

import fetchez.core as core


pytestmark = pytest.mark.usefixtures("no_retry_sleep")
URL = "https://example.invalid/bathymetry/grid.nc"


class FakeResponse:
    def __init__(
        self,
        status=200,
        *,
        body=b"data",
        headers=None,
        fail_during_stream=None,
    ):
        self.status_code = status
        self.content = body
        self.text = body.decode("utf-8", errors="replace")
        self.headers = CaseInsensitiveDict(
            {"Content-Length": str(len(body))} if headers is None else headers
        )
        self.url = "https://example.test/data"
        self.closed = False
        self.fail_during_stream = fail_during_stream

    def __bool__(self):
        return self.status_code < 400

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=8192):
        if self.fail_during_stream:
            raise self.fail_during_stream
        yield self.content

    def json(self):
        return {"message": "remote failure"}


@pytest.fixture(autouse=True)
def no_retries_wait(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    # core.STOP_EVENT.clear()
    yield
    # core.STOP_EVENT.clear()


def make_fetch(monkeypatch, responses, *, url="https://example.test/data"):
    fetch = core.Fetch(url)
    responses = iter(responses)
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        result = next(responses)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(fetch.session, "request", request)
    return fetch, calls


def test_fetch_req_success_returns_live_response(monkeypatch):
    response = FakeResponse(200)
    fetch, calls = make_fetch(monkeypatch, [response])
    assert fetch.fetch_req(tries=1) is response
    assert len(calls) == 1
    assert not response.closed  # Caller owns a returned streaming response.
    response.close()


def test_fetch_req_retries_gateway_timeout_and_closes_old_response(monkeypatch):
    temporary = FakeResponse(504)
    success = FakeResponse(200)
    fetch, calls = make_fetch(monkeypatch, [temporary, success])
    assert fetch.fetch_req(tries=2) is success
    assert temporary.closed
    assert len(calls) == 2


def test_fetch_req_exhausted_transport_errors_raise_with_cause(monkeypatch):
    fetch, calls = make_fetch(
        monkeypatch, [requests.Timeout("slow"), requests.Timeout("slow")]
    )
    with pytest.raises(core.FetchError, match="Timeout: slow") as exc:
        fetch.fetch_req(tries=2)
    assert isinstance(exc.value.__cause__, requests.Timeout)
    assert len(calls) == 2


def test_fetch_req_does_not_retry_permanent_http_404(monkeypatch):
    response = FakeResponse(404)
    fetch, calls = make_fetch(
        monkeypatch, [response, FakeResponse(404), FakeResponse(404)]
    )
    with pytest.raises(core.FetchError, match="HTTP 404") as _exc:
        fetch.fetch_req(tries=3)
    assert len(calls) == 1


def test_fetch_req_range_416_closes_response_and_preserves_configured_headers(
    monkeypatch,
):
    failed = FakeResponse(416)
    success = FakeResponse(200)
    fetch, calls = make_fetch(monkeypatch, [failed, success])
    fetch.headers["Range"] = "bytes=100-"
    assert fetch.fetch_req(tries=2) is success
    assert failed.closed
    assert (
        fetch.headers["Range"] == "bytes=100-"
    )  # Retry should use request-local headers.
    assert "Range" not in calls[1]["headers"]


def test_fetch_xml_propagates_network_failure(monkeypatch):
    fetch = core.Fetch("https://example.test/metadata.xml")
    monkeypatch.setattr(
        fetch,
        "fetch_req",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("outage")),
    )
    with pytest.raises(ConnectionError, match="outage") as _exc:
        fetch.fetch_xml()


def test_fetch_xml_rejects_malformed_xml(monkeypatch):
    fetch = core.Fetch("https://example.test/metadata.xml")
    monkeypatch.setattr(
        fetch, "fetch_req", lambda **kwargs: FakeResponse(200, body=b"not xml")
    )
    with pytest.raises(etree.XMLSyntaxError) as _exc:
        fetch.fetch_xml()


def test_fetch_file_complete_download_atomically_promotes_part(monkeypatch, tmp_path):
    fetch, calls = make_fetch(monkeypatch, [FakeResponse(200, body=b"abcdef")])
    target = tmp_path / "download.bin"
    assert fetch.fetch_file(target, tries=1, verbose=False) == 0
    assert target.read_bytes() == b"abcdef"
    assert not Path(str(target) + ".part").exists()
    assert len(calls) == 1


def test_fetch_file_incomplete_download_is_not_success(monkeypatch, tmp_path):
    response = FakeResponse(
        200,
        body=b"abc",
        headers={"content-length": "10"},
    )
    fetch, calls = make_fetch(monkeypatch, [response])
    target = tmp_path / "truncated.bin"

    with pytest.raises(core.FetchRetryExhausted) as caught:
        fetch.fetch_file(target, tries=1, verbose=False)

    assert isinstance(
        caught.value.__cause__,
        core.IncompleteDownloadError,
    )

    assert caught.value.attempts == 1
    assert len(calls) == 1
    assert not target.exists()
    assert Path(f"{target}.part").read_bytes() == b"abc"


def test_fetch_file_local_missing_returns_failure_code(tmp_path):
    target = tmp_path / "copy.bin"
    fetch = core.Fetch(f"file://{tmp_path / 'missing.bin'}")
    with pytest.raises(core.FetchError, match="Local copy failed") as _exc:
        fetch.fetch_file(target, verbose=False)
    assert not target.exists()


def test_fetch_file_cancellation_is_execution_scoped(monkeypatch, tmp_path):
    event = threading.Event()

    cancelled = core.Fetch(
        "https://example.test/cancel.bin",
        cancel_event=event,
    )

    event.set()

    target = tmp_path / "cancel.bin"

    def unexpected_request(**kwargs):
        pytest.fail("Cancelled download attempted a network request")

    monkeypatch.setattr(
        cancelled.session,
        "request",
        unexpected_request,
    )

    with pytest.raises(core.FetchCancelled, match="Fetch Cancelled") as _exc:
        cancelled.fetch_file(target, tries=1, verbose=False)

    assert not target.exists()


def test_fetch_contexts_are_independent():
    a = core.FetchExecutionContext()
    b = core.FetchExecutionContext()

    a.cancel()

    assert a.cancelled
    assert not b.cancelled


def test_fetch_ftp_failure_releases_connection(monkeypatch, tmp_path):
    fake_ftp = Mock()
    fake_ftp.size.return_value = 4
    fake_ftp.retrbinary.side_effect = ftplib.error_temp("temporary FTP failure")
    monkeypatch.setattr(ftplib, "FTP", lambda host: fake_ftp)
    fetch = core.Fetch("ftp://example.test/remote.bin")
    target = tmp_path / "ftp.bin"
    with pytest.raises(
        core.FetchError, match="FTP Error: temporary FTP failure"
    ) as _exc:
        fetch.fetch_ftp_file(target)

    assert not target.exists()
    assert fake_ftp.quit.called or fake_ftp.close.called


def test_fetch_ftp_respects_existing_destination(monkeypatch, tmp_path):
    target = tmp_path / "ftp.bin"
    target.write_bytes(b"keep")
    fake_ftp = Mock()
    fake_ftp.size.return_value = 4
    fake_ftp.retrbinary.side_effect = lambda command, callback: callback(b"new!")
    monkeypatch.setattr(ftplib, "FTP", lambda host: fake_ftp)
    fetch = core.Fetch("ftp://example.test/remote.bin")
    assert fetch.fetch_ftp_file(target, overwrite=False) == 0
    assert target.read_bytes() == b"keep"
    fake_ftp.retrbinary.assert_not_called()


def test_fetch_req_416_retries_without_range_even_with_one_try(monkeypatch):
    fetch = core.Fetch(
        "https://example.test/data.bin",
        headers={"Range": "bytes=999999-"},
    )

    requested_headers = []
    responses = []

    def fake_request(**kwargs):
        requested_headers.append(kwargs["headers"].copy())

        response = requests.Response()
        response.raw = io.BytesIO(b"")
        response.status_code = 416 if "Range" in kwargs["headers"] else 200
        response.url = kwargs["url"]

        responses.append(response)
        return response

    monkeypatch.setattr(fetch.session, "request", fake_request)

    response = fetch.fetch_req(tries=1)

    assert response.status_code == 200
    assert len(requested_headers) == 2
    assert requested_headers[0]["Range"] == "bytes=999999-"
    assert "Range" not in requested_headers[1]

    assert responses[0].raw.closed
    assert fetch.headers["Range"] == "bytes=999999-"

    response.close()


def test_fetch_ftp_mid_transfer_cancellation(monkeypatch, tmp_path):
    from unittest.mock import Mock
    import ftplib
    import threading

    event = threading.Event()
    fake_ftp = Mock()
    fake_ftp.size.return_value = 8

    def transfer(command, callback):
        callback(b"abcd")
        event.set()
        callback(b"efgh")

    fake_ftp.retrbinary.side_effect = transfer
    monkeypatch.setattr(ftplib, "FTP", lambda host: fake_ftp)

    fetch = core.Fetch(
        "ftp://example.test/data.bin",
        cancel_event=event,
    )

    target = tmp_path / "data.bin"

    with pytest.raises(core.FetchCancelled, match="FTP download cancelled") as _exc:
        fetch.fetch_ftp_file(target)

    assert not target.exists()
    fake_ftp.quit.assert_called_once()


@pytest.fixture
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)


@pytest.fixture
def fetcher():
    """Bypass Fetch.__init__ so tests never construct an HTTP session."""
    obj = object.__new__(core.Fetch)
    obj.url = URL
    obj.headers = {}
    obj.auth = None
    obj.verify = True
    obj.allow_redirects = True
    obj.cancel_event = None
    obj.silent = True
    obj.session = SimpleNamespace(request=None)
    return obj


class ResponseStub:
    def __init__(self, status=200, chunks=(b"abc",), headers=None):
        self.status_code = status
        self.headers = headers if headers is not None else {"content-length": "3"}
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size):
        yield from self.chunks

    def json(self):
        return {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} upstream error")


class FakeModule:
    name = "fake-provider"

    def __init__(self, results, fetch):
        self.results = results
        self.hooks = []
        self._fetch = fetch
        self._execution_context = None

    def fetch_entry(self, entry, check_size=True, verbose=True):
        return self._fetch(entry)


def _run(entries, fetch, *, ignore_failures=False, hooks=()):
    module = FakeModule(entries, fetch)
    return core.run_fetchez(
        [module],
        threads=1,
        global_hooks=list(hooks),
        ignore_failures=ignore_failures,
    )


def _error_text(exc):
    """Include chain because the executor may wrap lower-level exceptions."""
    parts = []
    while exc is not None and exc not in parts:
        parts.append(exc)
        exc = exc.__cause__
    return " | ".join(f"{type(x).__name__}: {x}" for x in parts)


def test_http_success_preserves_zero_return(fetcher, tmp_path):
    fetcher.session.request = lambda **kw: ResponseStub()
    target = tmp_path / "grid.nc"
    assert fetcher.fetch_file(target, tries=1, verbose=False) == 0
    assert target.read_bytes() == b"abc"
    assert not Path(f"{target}.part").exists()


def test_cached_file_returns_zero_without_network(fetcher, tmp_path):
    target = tmp_path / "cached.nc"
    target.write_bytes(b"cached")
    fetcher.session.request = lambda **kw: pytest.fail("unexpected request")
    assert fetcher.fetch_file(target, verbose=False) == 0


def test_worker_exception_preserves_original_cause(tmp_path):
    entry = {"dst_fn": str(tmp_path / "missing.nc"), "url": URL}

    def fail(_):
        raise ConnectionError("upstream THREDDS refused connection")

    with pytest.raises(RuntimeError) as caught:
        _run([entry], fail)
    assert isinstance(caught.value.__cause__, ConnectionError)
    assert "THREDDS refused connection" in _error_text(caught.value)


def test_ignore_failures_continues_and_annotates_failed_entry(tmp_path):
    entries = [
        {"dst_fn": str(tmp_path / "bad.nc"), "url": URL},
        {"dst_fn": str(tmp_path / "good.nc"), "url": "https://example.invalid/good.nc"},
    ]

    def fetch(entry):
        if Path(entry["dst_fn"]).name == "bad.nc":
            raise ConnectionError("server unavailable")
        return 0

    result = _run(entries, fetch, ignore_failures=True)
    by_name = {Path(e["dst_fn"]).name: e for _, e in result}
    assert by_name["bad.nc"]["status"] == "failed"
    assert "server unavailable" in by_name["bad.nc"]["error_message"]
    assert "good.nc" in by_name


def test_legacy_minus_one_is_rejected_in_strict_mode(tmp_path):
    entry = {"dst_fn": str(tmp_path / "bad.nc"), "url": URL}
    with pytest.raises(RuntimeError, match="non-zero status code: -1") as _exc:
        _run([entry], lambda _: -1)


def test_legacy_minus_one_is_recorded_in_continue_mode(tmp_path):
    entry = {"dst_fn": str(tmp_path / "bad.nc"), "url": URL}
    results = _run([entry], lambda _: -1, ignore_failures=True)
    assert results[0][1]["status"] == "failed"


def test_execution_context_cancel_flag():
    ctx = core.FetchExecutionContext()
    assert not ctx.cancelled
    ctx.cancel()
    assert ctx.cancelled


def test_worker_passes_through_success_and_exception():
    entry = {"dst_fn": "unused.nc"}
    good = FakeModule([entry], lambda _: 0)
    status = core._fetch_worker(good, entry)
    assert status == 0
    # print(status)
    # assert status.status == 0#"success"
    bad = FakeModule(
        [entry], lambda _: (_ for _ in ()).throw(OSError("disk unavailable"))
    )
    with pytest.raises(OSError, match="disk unavailable") as _exc:
        core._fetch_worker(bad, entry)


def test_connection_refused_raises_contextual_error(fetcher, tmp_path):
    calls = []

    def refused(**kwargs):
        calls.append(kwargs)
        raise requests.ConnectionError("connection refused")

    fetcher.session.request = refused
    with pytest.raises(Exception) as caught:
        fetcher.fetch_file(tmp_path / "grid.nc", tries=3, verbose=False)
    chain = _error_text(caught.value)
    assert "connection refused" in chain.lower()
    assert URL in chain
    assert "3" in chain  # total attempts in final diagnostic
    assert len(calls) == 3
    assert isinstance(caught.value.__cause__, requests.ConnectionError)


def test_midstream_failure_raises_original_cause(fetcher, tmp_path):
    def broken_stream():
        yield b"a"
        raise requests.ConnectionError("stream dropped halfway")

    fetcher.session.request = lambda **kwargs: ResponseStub(
        chunks=broken_stream(), headers={"content-length": "10"}
    )
    with pytest.raises(Exception) as caught:
        fetcher.fetch_file(tmp_path / "partial.nc", tries=1, verbose=False)
    assert "stream dropped halfway" in _error_text(caught.value)
    assert not (tmp_path / "partial.nc").exists()


def test_missing_local_source_raises(fetcher, tmp_path):
    absent = tmp_path / "missing.nc"
    fetcher.url = absent.as_uri()
    with pytest.raises(Exception) as caught:
        fetcher.fetch_file(absent, verbose=False)
    assert str(absent) in _error_text(caught.value)


def test_pre_cancelled_http_is_not_status_minus_one(fetcher, tmp_path):
    fetcher.cancel_event = threading.Event()
    fetcher.cancel_event.set()
    with pytest.raises(Exception) as caught:
        fetcher.fetch_file(tmp_path / "grid.nc", verbose=False)
    assert "cancel" in type(caught.value).__name__.lower()


def test_cancelled_worker_raises_fetch_cancelled():
    context = core.FetchExecutionContext()
    context.cancel()

    entry = {"dst_fn": "ignored.nc"}
    module = FakeModule(
        [entry],
        lambda _: pytest.fail("cancelled worker ran"),
    )

    with pytest.raises(core.FetchCancelled) as _exc:
        core._fetch_worker(module, entry, context=context)


def test_ftp_failure_raises_and_cleans_partial(fetcher, tmp_path, monkeypatch):
    import ftplib

    fetcher.url = "ftp://example.invalid/grid.nc"

    def fail_ftp(_host):
        raise OSError("ftp service unavailable")

    monkeypatch.setattr(ftplib, "FTP", fail_ftp)
    target = tmp_path / "grid.nc"
    with pytest.raises(Exception) as caught:
        fetcher.fetch_ftp_file(target)
    assert "ftp service unavailable" in _error_text(caught.value)
    assert not target.exists()


def test_lock_timeout_raises(fetcher, tmp_path, monkeypatch):
    import filelock

    class Locked:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise filelock.Timeout("busy.lock")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(core.filelock, "FileLock", Locked)
    with pytest.raises(Exception) as caught:
        fetcher.fetch_file(tmp_path / "grid.nc", verbose=False)
    assert "lock" in _error_text(caught.value).lower()


def test_failed_entry_exposes_structured_error(tmp_path):
    entry = {"dst_fn": str(tmp_path / "bad.nc"), "url": URL}

    def fail(_):
        raise ConnectionError("connection refused")

    results = _run([entry], fail, ignore_failures=True)
    error = results[0][1]["error"]
    assert isinstance(error, dict)
    assert error["stage"] == "fetch"
    assert "ConnectionError" in error["type"]
    assert "connection refused" in error["message"]


def test_exhaustion_logs_diagnostic_at_default_level(fetcher, tmp_path, caplog):
    fetcher.session.request = lambda **kwargs: (_ for _ in ()).throw(
        requests.ConnectionError("THREDDS connection refused")
    )
    entry = {"dst_fn": str(tmp_path / "grid.nc"), "url": URL}
    module = FakeModule(
        [entry],
        lambda _: fetcher.fetch_file(tmp_path / "grid.nc", tries=2, verbose=False),
    )
    with caplog.at_level(logging.INFO, logger="fetchez.core"):
        with pytest.raises(Exception) as _exc:
            core.run_fetchez([module], threads=1)
    diagnostics = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )
    assert URL in diagnostics
    assert "ConnectionError" in diagnostics
    assert "THREDDS connection refused" in diagnostics
    assert "2" in diagnostics


@pytest.mark.parametrize("status", [401, 403, 404])
def test_auth_failure_is_not_retried(fetcher, tmp_path, status):
    calls = []

    def unauthorized(**kwargs):
        calls.append(1)
        return ResponseStub(status=status)

    fetcher.session.request = unauthorized
    with pytest.raises(Exception) as _exc:
        fetcher.fetch_file(tmp_path / "grid.nc", tries=4, verbose=False)
    assert len(calls) == 1


def test_ignore_failures_does_not_swallow_cancellation(tmp_path):
    from fetchez.core import FetchCancelled

    entry = {"dst_fn": str(tmp_path / "bad.nc"), "url": URL}

    # class FetchCancelled(Exception):
    #    pass

    def cancel(_):
        raise FetchCancelled("user cancelled")

    with pytest.raises((KeyboardInterrupt, FetchCancelled)) as _exc:
        _run([entry], cancel, ignore_failures=True)


def test_midstream_cancellation_propagates(fetcher, tmp_path):
    cancel_event = threading.Event()
    fetcher.cancel_event = cancel_event

    def chunks():
        yield b"first"
        cancel_event.set()
        yield b"second"

    fetcher.session.request = lambda **kwargs: ResponseStub(chunks=chunks())

    with pytest.raises(core.FetchCancelled) as _exc:
        fetcher.fetch_file(
            tmp_path / "grid.nc",
            tries=3,
            verbose=False,
        )


@pytest.mark.parametrize(
    "status, expected",
    [
        (200, False),
        (206, False),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (408, True),
        (410, False),
        (429, True),
        (500, True),
        (501, False),
        (502, True),
        (503, True),
        (504, True),
    ],
)
def test_transient_http_status(status, expected):
    assert core._is_transient(status) is expected
