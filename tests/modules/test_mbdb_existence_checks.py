"""MBDB's per-file existence checks must not drop files when the server is busy.

Each survey's .fbt is checked with a HEAD request before it is listed. A
timeout or a 5xx used to read as "file does not exist", so a busy server
silently shortened the list (and the short list was cached). Now only a
404/410 means missing; other failures are retried, and a file that still
cannot be checked is kept, logged, and the list is not cached.
"""

import json
import logging
from typing import ClassVar

import pytest
import requests

from fetchez import spatial
from fetchez.modules import multibeam

REGION = spatial.Region(-121.30, -120.95, 35.45, 35.80, srs="EPSG:4326")
LOGGER = "fetchez.modules.multibeam"
DATA = "ocean/ships/x/v1/MB/line00001.mb58.gz"
PLAIN = f"{multibeam.NCEI_DATA_URL}ocean/ships/x/v1/MB/line00001.mb58.fbt"
GENERATED = f"{multibeam.NCEI_DATA_URL}ocean/ships/x/v1/MB/generated/line00001.mb58.fbt"


class FakeQuery:
    """One page holding the single survey DATA."""

    def __init__(self, url):
        self.url = url

    def fetch_req(self, params=None):
        payload = {"features": [{"attributes": {"DATA_FILE": DATA}}]}

        class Response:
            status_code = 200
            text = json.dumps(payload)

            def json(self):
                return payload

        return Response()


class FakeHead:
    """HEAD answers per URL: a list of status codes or exceptions, used in order."""

    answers: ClassVar[dict] = {}
    calls: ClassVar[list] = []

    @classmethod
    def head(cls, url, **kwargs):
        cls.calls.append(url)
        queue = cls.answers.get(url, [404])
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        response = requests.Response()
        response.status_code = answer
        return response


@pytest.fixture(autouse=True)
def fake_server(monkeypatch):
    FakeHead.answers = {}
    FakeHead.calls = []
    monkeypatch.setattr(multibeam.core, "Fetch", FakeQuery)
    monkeypatch.setattr(multibeam.requests, "head", FakeHead.head)
    monkeypatch.setattr(multibeam.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        multibeam.MBDB, "check_inf_region", lambda self, url: ("", None)
    )


def _run(tmp_path):
    mod = multibeam.MBDB(src_region=REGION, outdir=str(tmp_path), want_inf=False)
    mod.run()
    return mod


def _cache_files(tmp_path):
    return list((tmp_path / "mbdb" / ".fetchez_cache").glob("mbdb_*.json"))


def test_existing_generated_file_is_listed_with_one_check(tmp_path):
    FakeHead.answers = {GENERATED: [200]}
    mod = _run(tmp_path)

    assert [r["url"] for r in mod.results] == [GENERATED]
    assert FakeHead.calls == [GENERATED]
    assert mod._discovery_failed is False
    assert len(_cache_files(tmp_path)) == 1


def test_plain_path_is_used_only_when_generated_is_missing(tmp_path):
    FakeHead.answers = {GENERATED: [404], PLAIN: [200]}
    mod = _run(tmp_path)

    assert [r["url"] for r in mod.results] == [PLAIN]
    assert mod._discovery_failed is False


def test_file_missing_everywhere_is_dropped_quietly(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeHead.answers = {GENERATED: [404], PLAIN: [404]}
    mod = _run(tmp_path)

    assert mod.results == []
    assert mod._discovery_failed is False
    assert not caplog.records
    assert len(_cache_files(tmp_path)) == 1


def test_transient_failure_is_retried(tmp_path):
    FakeHead.answers = {GENERATED: [requests.Timeout("slow"), 503, 200]}
    mod = _run(tmp_path)

    assert [r["url"] for r in mod.results] == [GENERATED]
    assert FakeHead.calls == [GENERATED] * 3
    assert mod._discovery_failed is False


@pytest.mark.parametrize(
    "failure",
    [requests.Timeout("slow"), requests.ConnectionError("reset"), 503, 429],
    ids=["timeout", "connection-error", "503", "429"],
)
def test_file_that_cannot_be_checked_is_kept_and_flagged(tmp_path, caplog, failure):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeHead.answers = {GENERATED: [failure]}
    mod = _run(tmp_path)

    assert [r["url"] for r in mod.results] == [GENERATED]
    assert PLAIN not in FakeHead.calls, "a busy server must not trigger the fallback"
    assert mod._discovery_failed is True
    assert any("could not check" in r.getMessage() for r in caplog.records)
    assert _cache_files(tmp_path) == [], "an unverified list must not be cached"
