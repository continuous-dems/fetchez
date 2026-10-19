"""Exercise real Fetchez Fetch transport behavior without external network."""

import io

import requests
import pytest

from fetchez import core


def _response(status):
    response = requests.Response()
    response.status_code = status
    response.url = "https://tnmaccess.nationalmap.gov/api/v1/products"
    response.raw = io.BytesIO(b"")
    return response


def test_fetch_preserves_timeout_after_exhausted_attempts(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    attempts = []

    def fail(**kwargs):
        attempts.append(kwargs)
        raise requests.exceptions.ConnectTimeout("TNM connection timed out")

    monkeypatch.setattr(fetch.session, "request", fail)
    with pytest.raises(
        ConnectionError, match="ConnectTimeout: TNM connection timed out"
    ) as error:
        fetch.fetch_req(tries=2)
    assert isinstance(error.value.__cause__, requests.exceptions.ConnectTimeout)
    assert len(attempts) == 2


def test_fetch_recovers_after_temporary_gateway_failure(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    failed = _response(504)
    failed.raw = io.BytesIO(b"")
    recovered = _response(200)
    replies = iter((failed, recovered))
    monkeypatch.setattr(fetch.session, "request", lambda **_: next(replies))
    assert fetch.fetch_req(tries=2) is recovered
    assert failed.raw.closed


def test_fetch_preserves_http_status_after_exhausted_attempts(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    monkeypatch.setattr(fetch.session, "request", lambda **_: _response(503))
    with pytest.raises(ConnectionError, match="HTTPError: 503 Server Error") as error:
        fetch.fetch_req(tries=2)
    assert isinstance(error.value.__cause__, requests.HTTPError)


def test_fetch_does_not_masquerade_permanent_bad_request_as_timeout(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    monkeypatch.setattr(fetch.session, "request", lambda **_: _response(400))
    with pytest.raises(ConnectionError, match="HTTPError: 400 Client Error") as error:
        fetch.fetch_req(tries=2)
    assert isinstance(error.value.__cause__, requests.HTTPError)


def test_fetch_preserves_gateway_status_after_exhausted_attempts(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    monkeypatch.setattr(fetch.session, "request", lambda **_: _response(504))
    with pytest.raises(
        ConnectionError, match="HTTPError: 504 Gateway Timeout"
    ) as error:
        fetch.fetch_req(tries=2)
    assert isinstance(error.value.__cause__, requests.HTTPError)


def test_fetch_preserves_rate_limit_status_after_exhausted_attempts(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch("https://tnmaccess.nationalmap.gov/api/v1/products")
    monkeypatch.setattr(fetch.session, "request", lambda **_: _response(429))
    with pytest.raises(
        ConnectionError, match="HTTPError: 429 Too Many Requests"
    ) as error:
        fetch.fetch_req(tries=2)
    assert isinstance(error.value.__cause__, requests.HTTPError)
