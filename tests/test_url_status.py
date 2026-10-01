"""core.url_status / core.get_html_page: which failures are retried, and which are final.

Only failures a retry can fix (timeouts, connection errors, 408, 429, 5xx) may
end as 'unknown', which callers treat as "do not cache the list". Answers that
will never change (404/410, other client errors, redirect loops, bad URLs) are
final, so a perfectly healthy server can never keep a list from being cached.
A server that refuses HEAD (405, 501) is asked for one byte with GET instead.
"""

import io
import logging
from typing import ClassVar

import pytest
import requests

from fetchez import core

URL = "https://example.test/data/file.fbt"
PAGE = "https://example.test/data/"


class FakeWeb:
    """Answers per (method, url): a list of status codes, (status, text) or exceptions."""

    answers: ClassVar[dict] = {}
    calls: ClassVar[list] = []

    @classmethod
    def _answer(cls, method, url, kwargs):
        cls.calls.append((method, url, kwargs.get("headers")))
        queue = cls.answers.get((method, url), [404])
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        response = requests.Response()
        if isinstance(answer, tuple):
            response.status_code, text = answer
            response._content = text.encode()
        else:
            response.status_code = answer
            response._content = b""
        response.raw = io.BytesIO(response._content)
        return response

    @classmethod
    def head(cls, url, **kwargs):
        return cls._answer("HEAD", url, kwargs)

    @classmethod
    def get(cls, url, **kwargs):
        return cls._answer("GET", url, kwargs)


@pytest.fixture(autouse=True)
def fake_web(monkeypatch):
    FakeWeb.answers = {}
    FakeWeb.calls = []
    monkeypatch.setattr(core.requests, "head", FakeWeb.head)
    monkeypatch.setattr(core.requests, "get", FakeWeb.get)
    monkeypatch.setattr(core.time, "sleep", lambda _: None)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ([200], "exists"),
        ([302], "exists"),
        ([404], "missing"),
        ([410], "missing"),
        ([503, 200], "exists"),
        ([requests.Timeout("slow"), 200], "exists"),
        ([429, 408, 200], "exists"),
        ([500], "unknown"),
        ([503], "unknown"),
        ([requests.ConnectionError("reset")], "unknown"),
    ],
    ids=[
        "200",
        "302",
        "404",
        "410",
        "503-then-200",
        "timeout-then-200",
        "429-408-then-200",
        "persistent-500",
        "persistent-503",
        "persistent-connection-error",
    ],
)
def test_url_status_retries_only_transient_failures(answers, expected):
    FakeWeb.answers = {("HEAD", URL): answers}
    assert core.url_status(URL) == expected


@pytest.mark.parametrize("status", [400, 401, 403, 451])
def test_other_client_errors_are_final_and_logged(status, caplog):
    caplog.set_level(logging.WARNING, logger="fetchez.core")
    FakeWeb.answers = {("HEAD", URL): [status]}

    assert core.url_status(URL) == "missing"
    assert len(FakeWeb.calls) == 1, "a client error must not be retried"
    assert any(str(status) in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "error",
    [
        requests.TooManyRedirects("loop"),
        requests.exceptions.InvalidURL("bad"),
        requests.exceptions.MissingSchema("bad"),
    ],
    ids=["redirect-loop", "invalid-url", "missing-schema"],
)
def test_requests_that_cannot_succeed_are_final(error):
    FakeWeb.answers = {("HEAD", URL): [error]}

    assert core.url_status(URL) == "missing"
    assert len(FakeWeb.calls) == 1


@pytest.mark.parametrize("refusal", [405, 501])
@pytest.mark.parametrize(
    ("get_answer", "expected"),
    [
        (206, "exists"),
        (200, "exists"),
        (416, "exists"),
        (404, "missing"),
        (500, "unknown"),
    ],
    ids=["206", "200", "416-empty-file", "404", "persistent-500"],
)
def test_head_refused_falls_back_to_one_byte_get(refusal, get_answer, expected):
    FakeWeb.answers = {("HEAD", URL): [refusal], ("GET", URL): [get_answer]}

    assert core.url_status(URL) == expected
    gets = [c for c in FakeWeb.calls if c[0] == "GET"]
    assert gets and all(c[2] == {"Range": "bytes=0-0"} for c in gets)


@pytest.mark.parametrize(
    ("answers", "expected_status", "has_page"),
    [
        ([(200, "<html><a href='x'>x</a></html>")], "exists", True),
        ([404], "missing", False),
        ([403], "missing", False),
        ([503, (200, "<html></html>")], "exists", True),
        ([500], "unknown", False),
        ([requests.TooManyRedirects("loop")], "missing", False),
    ],
    ids=["200", "404", "403", "503-then-200", "persistent-500", "redirect-loop"],
)
def test_get_html_page(answers, expected_status, has_page):
    FakeWeb.answers = {("GET", PAGE): answers}
    page, status = core.get_html_page(PAGE)

    assert status == expected_status
    assert (page is not None) == has_page
