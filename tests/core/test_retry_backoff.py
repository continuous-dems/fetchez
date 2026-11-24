"""Retry backoff: exponential with full jitter, long enough to outlast a short block."""

import io

import pytest
import requests

from fetchez import api, core

URL = "https://example.test/data.nc"


def _response(status, headers=None):
    response = requests.Response()
    response.status_code = status
    response.url = URL
    response.raw = io.BytesIO(b"")
    if headers:
        response.headers.update(headers)
    return response


def _error(status, headers=None):
    return requests.HTTPError(f"HTTP {status}", response=_response(status, headers))


def test_retry_delay_is_capped_exponential_with_full_jitter(monkeypatch):
    bounds = []
    monkeypatch.setattr(
        core.random, "uniform", lambda low, high: bounds.append((low, high)) or high
    )
    fetch = core.Fetch(URL)

    for attempt in range(1, 13):
        fetch._retry_delay(attempt, requests.ConnectionError("refused"))

    assert [high for _, high in bounds] == [
        2,
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        300,
        300,
        300,
        300,
    ]
    assert {low for low, _ in bounds} == {0}


def test_retry_delay_is_jittered_within_its_bounds():
    fetch = core.Fetch(URL)
    error = requests.ConnectionError("refused")

    delays = [fetch._retry_delay(4, error) for _ in range(200)]

    assert all(0 <= delay <= 16 for delay in delays)
    assert len(set(delays)) > 1, "retries must not happen in lockstep"


def test_retry_after_on_rate_limit_is_still_honored():
    fetch = core.Fetch(URL)

    assert fetch._retry_delay(1, _error(429, {"Retry-After": "45"})) == 45
    assert fetch._retry_delay(1, _error(429, {"Retry-After": "9999"})) == 120


def test_default_retry_budget_outlasts_a_multi_minute_block(monkeypatch):
    waits = []
    monkeypatch.setattr(core.time, "sleep", waits.append)
    monkeypatch.setattr(core.random, "uniform", lambda low, high: high)
    fetch = core.Fetch(URL)
    attempts = []

    def refuse(**kwargs):
        attempts.append(kwargs)
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(fetch.session, "request", refuse)

    with pytest.raises(core.FetchRetryExhausted):
        fetch.fetch_req()

    assert len(attempts) == core.DEFAULT_TRIES
    assert len(waits) == core.DEFAULT_TRIES - 1
    assert sum(waits) > 10 * 60, "the longest schedule must outlast a 10 minute block"
    assert max(waits) == core.RETRY_BACKOFF_CAP


def test_tries_argument_still_limits_attempts(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    fetch = core.Fetch(URL)
    attempts = []

    def refuse(**kwargs):
        attempts.append(kwargs)
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(fetch.session, "request", refuse)

    with pytest.raises(core.FetchRetryExhausted):
        fetch.fetch_req(tries=3)

    assert len(attempts) == 3


class RecordingModule:
    name = "recording"

    def __init__(self, entries):
        self.results = entries
        self.hooks = []
        self.context = None
        self.retries = []

    def fetch_entry(
        self, entry, check_size=True, retries=core.DEFAULT_TRIES, verbose=True
    ):
        self.retries.append(retries)
        return 0

    def run(self):
        return self


def test_run_fetchez_passes_tries_to_the_module(tmp_path):
    module = RecordingModule([{"url": URL, "dst_fn": str(tmp_path / "a.nc")}])

    core.run_fetchez([module], threads=1, tries=3)

    assert module.retries == [3]


def test_run_fetchez_uses_the_module_default_without_tries(tmp_path):
    module = RecordingModule([{"url": URL, "dst_fn": str(tmp_path / "a.nc")}])

    core.run_fetchez([module], threads=1)

    assert module.retries == [core.DEFAULT_TRIES]


def test_get_passes_tries_to_run_fetchez(monkeypatch, tmp_path):
    class Module:
        def __init__(self, src_region=None, hook=None, outdir=None, **kwargs):
            self.results = [{"url": URL, "dst_fn": str(tmp_path / "a.nc")}]

        def run(self):
            return self

    seen = {}

    def fake_run_fetchez(modules, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(api.ModuleRegistry, "load_all", classmethod(lambda cls: None))
    monkeypatch.setattr(api.HookRegistry, "load_all", classmethod(lambda cls: None))
    monkeypatch.setattr(
        api.ModuleRegistry, "get_class", classmethod(lambda cls, name: Module)
    )
    monkeypatch.setattr(api, "run_fetchez", fake_run_fetchez)

    api.get("anything", tries=20)

    assert seen["tries"] == 20
