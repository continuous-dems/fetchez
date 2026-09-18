"""A TNM API outage must be reported as an error, never as "no products".

During an outage the API can answer HTTP 200 with a body such as
``{"error": "..."}``, return a non-JSON page, a non-200 status, or no
response at all. None of those is evidence that a region has no data, and
the (empty) results must not be cached, or later runs replay the outage as
a genuine empty answer.
"""

import json
import logging
from typing import ClassVar

import pytest

from fetchez import spatial
from fetchez.modules import tnm

REGION = spatial.Region(-118.65, -118.60, 34.05, 34.10, srs="EPSG:4326")
LOGGER = "fetchez.modules.tnm"


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None, json_error=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeFetch:
    """Returns the queued responses in order, repeating the last one."""

    responses: ClassVar[list] = []
    calls = 0

    def __init__(self, _url):
        pass

    def fetch_req(self, params=None):
        cls = self.__class__
        index = min(cls.calls, len(cls.responses) - 1)
        cls.calls += 1
        return cls.responses[index]


@pytest.fixture(autouse=True)
def fake_fetch(monkeypatch):
    FakeFetch.responses = []
    FakeFetch.calls = 0
    monkeypatch.setattr(tnm.core, "Fetch", FakeFetch)
    return FakeFetch


def _healthy(items, total=None):
    payload = {"total": len(items) if total is None else total, "items": items}
    return FakeResponse(payload=payload, text=json.dumps(payload))


def _item(name):
    url = f"https://example.test/StagedProducts/Elevation/1/TIFF/{name}.tif"
    return {
        "title": name,
        "downloadURL": url,
        "format": "GeoTIFF",
        "sizeInBytes": 1234,
        "publicationDate": "2024-01-01",
        "boundingBox": {"minX": -119, "maxX": -118, "minY": 34, "maxY": 35},
    }


OUTAGES = {
    "error_body": FakeResponse(
        payload={"error": "Service Unavailable"},
        text='{"error": "Service Unavailable"}',
    ),
    "error_message_body": FakeResponse(
        payload={"errorMessage": "Internal error", "total": 0, "items": []},
        text='{"errorMessage": "Internal error", "total": 0, "items": []}',
    ),
    "missing_fields": FakeResponse(payload={"message": "ok"}, text='{"message": "ok"}'),
    "non_dict_body": FakeResponse(payload=[], text="[]"),
    "non_json_body": FakeResponse(
        text="<html>502 Bad Gateway</html>", json_error=ValueError("No JSON")
    ),
    "http_503": FakeResponse(status_code=503, text="Service Unavailable"),
    "no_response": None,
}


def _module(tmp_path, **kwargs):
    return tnm.TheNationalMap(src_region=REGION, outdir=str(tmp_path), **kwargs)


def _cache_files(tmp_path):
    return list((tmp_path / "tnm" / ".fetchez_cache").glob("tnm_*.json"))


@pytest.mark.parametrize("outage", list(OUTAGES), ids=list(OUTAGES))
def test_outage_is_reported_as_an_error_not_zero_results(tmp_path, caplog, outage):
    FakeFetch.responses = [OUTAGES[outage]]
    caplog.set_level(logging.ERROR, logger=LOGGER)

    mod = _module(tmp_path)
    mod.run()

    assert mod.results == []
    assert mod._discovery_failed is True
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "an API outage must be logged as an error"
    assert any("TNM API" in r.getMessage() for r in errors)
    assert _cache_files(tmp_path) == [], "a failed query must not be cached"


@pytest.mark.parametrize("outage", list(OUTAGES), ids=list(OUTAGES))
def test_outage_raises_in_strict_mode(tmp_path, outage):
    FakeFetch.responses = [OUTAGES[outage]]

    mod = _module(tmp_path, strict_datasets=True)
    with pytest.raises(RuntimeError):
        mod.run()

    assert mod.results == []
    assert _cache_files(tmp_path) == []


def test_outage_raises_for_product_queries(tmp_path):
    FakeFetch.responses = [OUTAGES["error_body"]]

    mod = _module(tmp_path, products="1_as")
    with pytest.raises(RuntimeError):
        mod.run()

    assert _cache_files(tmp_path) == []


def test_genuine_empty_answer_is_still_cached(tmp_path, caplog):
    FakeFetch.responses = [_healthy([])]
    caplog.set_level(logging.ERROR, logger=LOGGER)

    mod = _module(tmp_path)
    mod.run()

    assert mod.results == []
    assert mod._discovery_failed is False
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    cached = _cache_files(tmp_path)
    assert len(cached) == 1
    assert json.loads(cached[0].read_text()) == []


def test_outage_after_first_page_keeps_partial_results_uncached(tmp_path):
    FakeFetch.responses = [
        _healthy([_item("USGS_1_n35w119")], total=150),
        OUTAGES["http_503"],
    ]

    mod = _module(tmp_path)
    mod.run()

    assert FakeFetch.calls == 2
    assert len(mod.results) == 1
    assert mod._discovery_failed is True
    assert _cache_files(tmp_path) == []


def test_query_is_cached_once_the_api_recovers(tmp_path):
    FakeFetch.responses = [OUTAGES["error_body"]]
    mod = _module(tmp_path)
    mod.run()
    assert mod._discovery_failed is True
    assert _cache_files(tmp_path) == []

    FakeFetch.responses = [_healthy([_item("USGS_1_n35w119")])]
    mod.run()

    assert mod._discovery_failed is False
    assert len(mod.results) == 1
    cached = _cache_files(tmp_path)
    assert len(cached) == 1
    assert len(json.loads(cached[0].read_text())) == 1


def test_outage_does_not_reuse_stale_state_with_cache_disabled(tmp_path):
    FakeFetch.responses = [OUTAGES["error_body"]]
    mod = _module(tmp_path, use_cache=False)
    mod.run()
    assert mod._discovery_failed is True

    FakeFetch.responses = [_healthy([])]
    mod.run()
    assert mod._discovery_failed is False
