"""The MBDB query must page past the MapServer's per-request record limit.

The multibeam_files MapServer returns at most ``maxRecordCount`` (2000)
features per request and sets ``exceededTransferLimit`` when more remain.
Without paging, a region with more surveys than that silently gets only the
first page. A page that fails must be reported, and the partial list must not
be cached as the region's answer.
"""

import json
import logging
from typing import ClassVar

import pytest

from fetchez import spatial
from fetchez.modules import multibeam

REGION = spatial.Region(-121.30, -120.95, 35.45, 35.80, srs="EPSG:4326")
LOGGER = "fetchez.modules.multibeam"


class FakeResponse:
    def __init__(self, payload=None, json_error=None):
        self.status_code = 200
        self._payload = payload
        self._json_error = json_error
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeFetch:
    """Answers query requests from ``pages`` by resultOffset; records them."""

    pages: ClassVar[dict] = {}
    calls: ClassVar[list] = []

    def __init__(self, url):
        self.url = url

    def fetch_req(self, params=None):
        FakeFetch.calls.append(dict(params or {}))
        return FakeFetch.pages.get((params or {}).get("resultOffset"))


def _features(start, count):
    return [
        {"attributes": {"DATA_FILE": f"ocean/ships/x/MB/line{i:05d}.mb58.gz"}}
        for i in range(start, start + count)
    ]


def _page(start, count, more):
    payload = {"features": _features(start, count)}
    if more:
        payload["exceededTransferLimit"] = True
    return FakeResponse(payload)


@pytest.fixture(autouse=True)
def fake_server(monkeypatch):
    FakeFetch.pages = {}
    FakeFetch.calls = []
    monkeypatch.setattr(multibeam.core, "Fetch", FakeFetch)
    monkeypatch.setattr(multibeam.MBDB, "_url_status", lambda self, url: "exists")
    monkeypatch.setattr(
        multibeam.MBDB, "check_inf_region", lambda self, url: ("", None)
    )


def _module(tmp_path):
    return multibeam.MBDB(src_region=REGION, outdir=str(tmp_path), want_inf=False)


def _cache_files(tmp_path):
    return list((tmp_path / "mbdb" / ".fetchez_cache").glob("mbdb_*.json"))


def test_query_pages_past_the_record_limit(tmp_path):
    FakeFetch.pages = {
        0: _page(0, 2000, more=True),
        2000: _page(2000, 2000, more=True),
        4000: _page(4000, 107, more=False),
    }
    mod = _module(tmp_path)
    mod.run()

    assert [c["resultOffset"] for c in FakeFetch.calls] == [0, 2000, 4000]
    assert all(c["orderByFields"] == "OBJECTID ASC" for c in FakeFetch.calls)
    assert len(mod.results) == 4107
    assert len({r["url"] for r in mod.results}) == 4107
    assert mod._discovery_failed is False
    assert len(_cache_files(tmp_path)) == 1


def test_single_page_makes_one_request(tmp_path):
    FakeFetch.pages = {0: _page(0, 12, more=False)}
    mod = _module(tmp_path)
    mod.run()

    assert len(FakeFetch.calls) == 1
    assert len(mod.results) == 12


@pytest.mark.parametrize(
    "bad_page",
    [
        None,
        FakeResponse({"error": {"code": 500, "message": "Error performing query"}}),
        FakeResponse(json_error=ValueError("not json")),
    ],
    ids=["no-response", "arcgis-error", "not-json"],
)
def test_failed_page_is_reported_and_not_cached(tmp_path, caplog, bad_page):
    caplog.set_level(logging.ERROR, logger=LOGGER)
    FakeFetch.pages = {0: _page(0, 2000, more=True), 2000: bad_page}
    mod = _module(tmp_path)
    mod.run()

    assert len(mod.results) == 2000
    assert mod._discovery_failed is True
    assert any("MBDB query failed" in r.getMessage() for r in caplog.records)
    assert _cache_files(tmp_path) == [], "a partial list must not be cached"
