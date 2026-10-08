"""A CMR search that fails must say so, not look like one that found nothing.

The search used to log an error and return no results when the request failed
or its answer could not be read. Callers that run a module directly (globato's
lookup of ICESat-2 ATL08/ATL24 granules, for one) then took an outage for a
granule that does not exist and carried on without it.
"""

import logging

import pytest

import fetchez
from fetchez.modules import earthdata


class FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def __bool__(self):
        # requests.Response is falsy for an HTTP error status.
        return self.status_code < 400

    def json(self):
        if self._bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


def _answer(monkeypatch, response):
    class FakeFetch:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_req(self, *args, **kwargs):
            return response

    monkeypatch.setattr(earthdata.core, "Fetch", FakeFetch)


def _search(tmp_path, **kwargs):
    module = earthdata.IceSat2(
        src_region=None,
        outdir=str(tmp_path),
        short_name="ATL08",
        filename_filter="20241107234251_08052501_007",
        version="",
        **kwargs,
    )
    module.run()
    return module


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (None, "no response"),
        (FakeResponse(status_code=503), "HTTP 503"),
    ],
)
def test_a_failed_search_raises(tmp_path, monkeypatch, response, message):
    _answer(monkeypatch, response)

    with pytest.raises(earthdata.EarthdataSearchError, match=message):
        _search(tmp_path)


def test_an_unreadable_answer_raises(tmp_path, monkeypatch):
    _answer(monkeypatch, FakeResponse(bad_json=True))

    with pytest.raises(earthdata.EarthdataSearchError, match="Could not read"):
        _search(tmp_path)


def test_a_search_that_finds_nothing_is_not_an_error(tmp_path, monkeypatch):
    _answer(monkeypatch, FakeResponse(payload={"feed": {"entry": []}}))

    assert _search(tmp_path).results == []


def test_fetchez_get_still_returns_nothing_for_a_failed_search(tmp_path, monkeypatch):
    """fetchez's own entry points catch it, as before: logged, and no results."""
    _answer(monkeypatch, None)

    assert (
        fetchez.get(
            "icesat2",
            outdir=str(tmp_path),
            short_name="ATL08",
            filename_filter="20241107234251_08052501_007",
            version="",
        )
        == []
    )


@pytest.mark.parametrize(
    "response",
    [None, FakeResponse(status_code=503), FakeResponse(bad_json=True)],
    ids=["no-response", "http-error", "unreadable"],
)
def test_with_raising_off_a_failed_search_warns_and_finds_nothing(
    tmp_path, monkeypatch, caplog, response
):
    """raise_on_search_error=False keeps going, but never silently."""
    _answer(monkeypatch, response)

    with caplog.at_level(logging.WARNING, logger="fetchez.modules.earthdata"):
        module = _search(tmp_path, raise_on_search_error=False)

    assert module.results == []
    assert "Treating it as no results" in caplog.text
