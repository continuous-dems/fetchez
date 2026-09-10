import io

import pytest
import requests

from fetchez.core import HttpFile


class Response:
    def __init__(self, status, headers, data=b""):
        self.status_code = status
        self.headers = headers
        self.data = io.BytesIO(data)
        self.raw = self
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def read(self, size, decode_content=False):
        self.reads += 1
        return self.data.read(size)


class Session:
    def __init__(self):
        self.payload = b"0123456789"
        self.head_response = Response(200, {"Content-Length": "10"})
        self.get_response = None
        self.ranges = []

    def head(self, url, **kwargs):
        return self.head_response

    def get(self, url, headers, **kwargs):
        assert kwargs["stream"] is True
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        self.ranges.append((start, end))
        return self.get_response or Response(
            206,
            {"Content-Range": f"bytes {start}-{end}/10"},
            self.payload[start : end + 1],
        )


def test_random_access_and_eof_only_read_requested_ranges():
    session = Session()
    sizes = []
    with HttpFile("https://example.test/archive.zip", session, sizes.append) as remote:
        assert remote.read(3) == b"012"
        remote.seek(-2, io.SEEK_END)
        assert remote.read() == b"89"
        assert remote.read() == b""
        remote.seek(2)
        assert remote.read(0) == b""
        assert remote.read(2) == b"23"
        assert remote.tell() == 4
    assert session.ranges == [(0, 2), (8, 9), (2, 3)]
    assert sizes == [3, 2, 2]


@pytest.mark.parametrize(
    ("response", "error"),
    [(Response(500, {}), requests.HTTPError), (Response(200, {}), OSError)],
)
def test_failed_or_missing_file_size_raises(response, error):
    session = Session()
    session.head_response = response
    with pytest.raises(error):
        HttpFile("https://example.test/archive.zip", session)


@pytest.mark.parametrize(
    "response",
    [
        Response(200, {}, b"0123456789"),
        Response(206, {"Content-Range": "bytes 0-2/11"}, b"012"),
        Response(206, {"Content-Range": "bytes 1-3/10"}, b"123"),
    ],
)
def test_ignored_or_inconsistent_range_is_rejected_before_body_read(response):
    session = Session()
    session.get_response = response
    with HttpFile("https://example.test/archive.zip", session) as remote:
        with pytest.raises(OSError, match="did not honor"):
            remote.read(3)
    assert response.reads == 0


@pytest.mark.parametrize("body", [b"01", b"0123"])
def test_truncated_or_oversized_range_is_rejected(body):
    session = Session()
    session.get_response = Response(206, {"Content-Range": "bytes 0-2/10"}, body)
    with HttpFile("https://example.test/archive.zip", session) as remote:
        with pytest.raises(OSError, match="incomplete byte range"):
            remote.read(3)
        assert remote.tell() == 0
