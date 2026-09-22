"""A Harmony job in its preview state must be skipped past, not abandoned.

Harmony answers a job over its preview threshold with the status ``previewing``:
it processes a small batch and then pauses until told to go on. The poll used
to treat that as an unknown status and stop, so a large request came back with
no results at all. It now asks Harmony to skip the preview and keeps polling.
"""

from typing import ClassVar

import pytest

from fetchez.modules import earthdata

JOB_ID = "abc-123"
DATA_URL = (
    "https://harmony.earthdata.nasa.gov/service-results/ATL03_x_007_01_subsetted.h5"
)


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class FakeFetch:
    """Answers status pings from a queue, repeating the last, and records every URL."""

    statuses: ClassVar[list] = []
    urls: ClassVar[list] = []

    def __init__(self, url, headers=None, auth=None):
        self.url = url
        self.__class__.urls.append(url)

    def fetch_req(self, timeout=None):
        cls = self.__class__
        # The poll retries forever on an exception, and sleep is stubbed out
        # here, so a broken poll would spin rather than fail. Cut it short.
        if len(cls.urls) > 20:
            raise AssertionError(f"polling did not finish: {cls.urls}")
        if self.url.endswith("/skip-preview"):
            return FakeResponse({"status": "running"})
        pings = sum(1 for u in cls.urls if u.endswith(f"/jobs/{JOB_ID}"))
        return FakeResponse(cls.statuses[min(pings - 1, len(cls.statuses) - 1)])


@pytest.fixture(autouse=True)
def fake_harmony(monkeypatch):
    FakeFetch.statuses = []
    FakeFetch.urls = []
    monkeypatch.setattr(earthdata.core, "Fetch", FakeFetch)
    monkeypatch.setattr(earthdata.core, "get_credentials", lambda **kwargs: None)
    monkeypatch.setattr(earthdata.time, "sleep", lambda seconds: None)
    return FakeFetch


def _module(tmp_path):
    return earthdata.IceSat2(
        src_region=None, outdir=str(tmp_path), subset=True, subset_job_id=JOB_ID
    )


def test_a_previewing_job_is_skipped_past_and_polled_to_completion(tmp_path):
    FakeFetch.statuses = [
        {"status": "previewing", "progress": 0},
        {"status": "running", "progress": 50},
        {"status": "successful", "progress": 100, "links": [{"href": DATA_URL}]},
    ]

    module = _module(tmp_path)
    module._run_harmony_subset()

    assert f"{earthdata.HARMONY_BASE_URL}/jobs/{JOB_ID}/skip-preview" in FakeFetch.urls
    assert [entry["url"] for entry in module.results] == [DATA_URL]


def test_a_job_that_pauses_after_its_preview_is_resumed(tmp_path):
    """If Harmony refuses the skip, the job pauses, and the existing resume path applies."""
    FakeFetch.statuses = [
        {"status": "previewing", "progress": 0},
        {"status": "paused", "progress": 5},
        {"status": "successful", "progress": 100, "links": [{"href": DATA_URL}]},
    ]

    module = _module(tmp_path)
    module._run_harmony_subset()

    assert f"{earthdata.HARMONY_BASE_URL}/jobs/{JOB_ID}/resume" in FakeFetch.urls
    assert [entry["url"] for entry in module.results] == [DATA_URL]


def test_skip_preview_is_an_accepted_ping_request(tmp_path):
    module = _module(tmp_path)

    module.harmony_ping_for_status(JOB_ID, "skip-preview")

    assert FakeFetch.urls == [
        f"{earthdata.HARMONY_BASE_URL}/jobs/{JOB_ID}/skip-preview"
    ]
