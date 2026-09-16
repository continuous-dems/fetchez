from unittest.mock import MagicMock, patch

import pytest

from fetchez.core import Fetch, R_HEADERS


@pytest.fixture(autouse=True)
def preserve_default_headers():
    with patch.dict(R_HEADERS):
        yield


def response(status, data=b"", **headers):
    result = MagicMock(
        status_code=status,
        headers={"content-length": str(len(data)), **headers},
    )
    result.__enter__.return_value = result
    result.iter_content.return_value = [data]
    return result


@pytest.mark.parametrize("headers", [None, {}, {"Authorization": "Bearer test"}])
def test_fetch_copies_default_and_caller_headers(headers):
    headers = None if headers is None else dict(headers)
    expected = dict(R_HEADERS if headers is None else headers)
    options = {} if headers is None else {"headers": headers}
    first = Fetch("https://example.test/first", **options)
    second = Fetch("https://example.test/second", **options)

    assert first.headers == expected
    first.headers["Range"] = "bytes=3-"

    assert second.headers == expected
    assert (R_HEADERS if headers is None else headers) == expected


@pytest.mark.parametrize("reuse_fetch", [False, True])
@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer test"}])
def test_resuming_a_download_does_not_change_other_requests(
    tmp_path, monkeypatch, reuse_fetch, headers
):
    headers = None if headers is None else dict(headers)
    options = {} if headers is None else {"headers": headers}
    expected = dict(R_HEADERS if headers is None else headers)
    fetch = Fetch("https://example.test/data", **options)
    other = fetch if reuse_fetch else Fetch("https://example.test/other", **options)
    partial = tmp_path / "first.part"
    partial.write_bytes(b"abc")
    request = MagicMock(
        side_effect=[
            response(206, b"def", **{"Content-Range": "bytes 3-5/6"}),
            response(200, b"abcdef"),
        ]
    )
    monkeypatch.setattr(fetch.session, "request", request)
    monkeypatch.setattr(other.session, "request", request)

    assert fetch.fetch_file(tmp_path / "first", verbose=False) == 0
    assert other.fetch_file(tmp_path / "second", verbose=False) == 0

    assert request.call_args_list[0].kwargs["headers"] == {
        **expected,
        "Range": "bytes=3-",
    }
    assert request.call_args_list[1].kwargs["headers"] == expected
    assert (tmp_path / "first").read_bytes() == b"abcdef"
    assert (tmp_path / "second").read_bytes() == b"abcdef"
    assert fetch.headers == other.headers == expected
    assert (R_HEADERS if headers is None else headers) == expected
    assert Fetch("https://example.test/later", **options).headers == expected


@pytest.mark.parametrize("headers", [{}, {"Range": "bytes=1-"}])
def test_invalid_range_retries_without_changing_configured_headers(
    tmp_path, monkeypatch, headers
):
    headers = dict(headers)
    expected = dict(headers)
    fetch = Fetch("https://example.test/data", headers=headers)
    (tmp_path / "data.part").write_bytes(b"abc")
    request = MagicMock(side_effect=[response(416), response(200, b"abcdef")])
    monkeypatch.setattr(fetch.session, "request", request)

    assert fetch.fetch_file(tmp_path / "data", verbose=False) == 0

    assert request.call_args_list[0].kwargs["headers"]["Range"] == "bytes=3-"
    assert "Range" not in request.call_args_list[1].kwargs["headers"]
    assert (tmp_path / "data").read_bytes() == b"abcdef"
    assert fetch.headers == headers == expected


def test_ignored_resume_restarts_without_changing_headers(tmp_path, monkeypatch):
    headers = {"Authorization": "Bearer test"}
    fetch = Fetch("https://example.test/data", headers=headers)
    (tmp_path / "data.part").write_bytes(b"abc")
    request = MagicMock(return_value=response(200, b"abcdef"))
    monkeypatch.setattr(fetch.session, "request", request)

    assert fetch.fetch_file(tmp_path / "data", verbose=False) == 0

    assert request.call_args.kwargs["headers"]["Range"] == "bytes=3-"
    assert (tmp_path / "data").read_bytes() == b"abcdef"
    assert fetch.headers == headers == {"Authorization": "Bearer test"}
