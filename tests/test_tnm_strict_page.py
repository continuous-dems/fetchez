"""Offline contracts for strict TNM pagination's real page-validation helper."""

import json

import pytest
import requests

from fetchez.modules import tnm_page


def _response(payload, status=200):
    response = requests.Response()
    response.status_code = status
    response.url = "https://tnmaccess.nationalmap.gov/api/v1/products"
    response._content = json.dumps(payload).encode()
    return response


def _fetch_sequence(pages):
    calls = []
    sequence = iter(pages)

    def fetch(params):
        calls.append(dict(params))
        return next(sequence)

    return fetch, calls


def test_transient_invalid_200_recovers_at_exact_offset(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    malformed = _response({"total": 3, "items": []})
    valid = _response(
        {"total": 3, "items": [{"downloadURL": "https://example.test/b"}]}
    )
    fetch, calls = _fetch_sequence([malformed, valid])
    result = tnm_page.fetch_strict_page(
        fetch,
        {"offset": 1, "datasets": "test"},
        1,
        3,
        {"https://example.test/a"},
        "test",
    )
    assert result is valid
    assert len(calls) == 2
    assert calls[0] == calls[1] == {"offset": 1, "datasets": "test"}
    assert not valid.raw or not valid.raw.closed
    assert malformed.raw is None or malformed.raw.closed


def test_persistent_invalid_page_fails_closed_with_specific_reason(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    fetch, calls = _fetch_sequence([_response({"items": []}) for _ in range(3)])
    with pytest.raises(ValueError, match="total is .* nonnegative integer") as failure:
        tnm_page.fetch_strict_page(fetch, {"offset": 100}, 100, 200, set(), "1m")
    assert "offset=100" in str(failure.value)
    assert "attempt=3/3" in str(failure.value)
    assert "response_sha256_prefix=" in str(failure.value)
    assert len(calls) == 3


def test_accepted_pages_are_not_replayed_after_later_page_retry(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    first = _response(
        {"total": 2, "items": [{"downloadURL": "https://example.test/a"}]}
    )
    repeated = _response(
        {"total": 2, "items": [{"downloadURL": "https://example.test/a"}]}
    )
    second = _response(
        {"total": 2, "items": [{"downloadURL": "https://example.test/b"}]}
    )
    fetch, calls = _fetch_sequence([first, repeated, second])
    assert (
        tnm_page.fetch_strict_page(fetch, {"offset": 0}, 0, None, set(), "1m") is first
    )
    assert (
        tnm_page.fetch_strict_page(
            fetch, {"offset": 1}, 1, 2, {"https://example.test/a"}, "1m"
        )
        is second
    )
    assert [call["offset"] for call in calls] == [0, 1, 1]


def test_drifting_total_never_becomes_no_coverage(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    fetch, _ = _fetch_sequence([_response({"total": 0, "items": []}) for _ in range(3)])
    with pytest.raises(ValueError, match="total changed from 2 to 0"):
        tnm_page.fetch_strict_page(fetch, {"offset": 1}, 1, 2, set(), "1m")


def test_semantic_rejection_and_non_200_are_not_retried(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    for payload, status in (
        ({"errorMessage": "invalid dataset", "items": [], "total": 0}, 200),
        ({"total": 0, "items": []}, 403),
    ):
        response = _response(payload, status)
        fetch, calls = _fetch_sequence([response])
        assert (
            tnm_page.fetch_strict_page(fetch, {"offset": 0}, 0, None, set(), "1m")
            is response
        )
        assert len(calls) == 1


def test_item_validity_checked_before_page_acceptance(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    fetch, calls = _fetch_sequence(
        [
            _response({"total": 1, "items": [None]}),
            _response({"total": 1, "items": [{}]}),
            _response(
                {"total": 1, "items": [{"downloadURL": "https://example.test/ok"}]}
            ),
        ]
    )
    result = tnm_page.fetch_strict_page(fetch, {"offset": 0}, 0, None, set(), "1m")
    assert result.json()["items"][0]["downloadURL"].endswith("/ok")
    assert len(calls) == 3


def test_partial_page_is_legal_when_total_is_consistent():
    response = _response(
        {"total": 12, "items": [{"downloadURL": "https://example.test/a"}]}
    )
    fetch, calls = _fetch_sequence([response])
    assert (
        tnm_page.fetch_strict_page(fetch, {"offset": 0}, 0, None, set(), "1m")
        is response
    )
    assert len(calls) == 1


def test_error_shaped_200_surfaces_actual_upstream_reason_without_retry(monkeypatch):
    monkeypatch.setattr(tnm_page.time, "sleep", lambda _: None)
    response = _response(
        {
            "error": True,
            "showToast": True,
            "toastMessage": "Upstream catalog unavailable",
            "toastType": "error",
        }
    )
    fetch, calls = _fetch_sequence([response])
    with pytest.raises(ValueError, match="Upstream catalog unavailable") as failure:
        tnm_page.fetch_strict_page(
            fetch,
            {"offset": 0},
            0,
            None,
            set(),
            "Digital Elevation Model (DEM) 1 meter",
        )
    assert "dataset='Digital Elevation Model (DEM) 1 meter'" in str(failure.value)
    assert len(calls) == 1


def test_error_shaped_page_cannot_be_misread_as_zero_coverage():
    response = _response(
        {
            "error": True,
            "toastType": "error",
            "toastMessage": "invalid query",
            "total": 0,
            "items": [],
        }
    )
    fetch, calls = _fetch_sequence([response])
    with pytest.raises(ValueError, match="invalid query"):
        tnm_page.fetch_strict_page(fetch, {"offset": 0}, 0, None, set(), "1m")
    assert len(calls) == 1
