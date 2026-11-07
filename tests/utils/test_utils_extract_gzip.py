# tests/utils/test_utils_extract_gzip.py

"""GZIP consistency for fetchez.utils.archives (issue #530, section 4).

``_extract_gzip()`` should stage and publish its output the same way the ZIP
and TAR paths do, and a failed decompression must never publish an
incomplete file or leave temporary files behind. Every input is built inside
pytest's ``tmp_path``; no network.
"""

import gzip
import os
import sys
import zipfile
from pathlib import Path

import pytest

from fetchez import utils
from fetchez.utils import archives

MEMBER = "resource.dat"
ORIGINAL = b"original data " * 64
PREVIOUS = b"previously extracted output"


def _make_gzip(path: Path, data: bytes = ORIGINAL) -> Path:
    path.write_bytes(gzip.compress(data))
    return path


def _leftovers(outdir: Path, *expected: str) -> list[str]:
    """Return entries in outdir other than the expected outputs and the lock."""
    return sorted(
        entry.name
        for entry in outdir.iterdir()
        if entry.name not in expected and not entry.name.endswith(".extract.lock")
    )


@pytest.fixture
def umask_022():
    previous = os.umask(0o022)
    try:
        yield 0o022
    finally:
        os.umask(previous)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
@pytest.mark.parametrize("overwrite", [False, True])
def test_gzip_output_permissions_match_zip(tmp_path, umask_022, overwrite):
    """GZIP outputs get the same umask-derived mode as ZIP and TAR outputs.

    They used to be published from a mkstemp() file, which is always 0600.
    """
    gz_path = _make_gzip(tmp_path / f"{MEMBER}.gz")
    zip_path = tmp_path / "input.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("from_zip.dat", ORIGINAL)

    outdir = tmp_path / "output"
    [gz_out] = utils.p_f_gunzip(gz_path, outdir=outdir, overwrite=overwrite)
    [zip_out] = utils.p_f_unzip(zip_path, outdir=outdir, overwrite=overwrite)

    expected = 0o666 & ~umask_022
    assert gz_out.stat().st_mode & 0o777 == expected
    assert zip_out.stat().st_mode & 0o777 == expected


class _InterruptedReader:
    """Stand-in for gzip.open() that yields some data, then is interrupted."""

    def __init__(self):
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size=-1):
        self.reads += 1
        if self.reads == 1:
            return b"partial"
        raise KeyboardInterrupt


def test_interrupted_gzip_leaves_no_temp_files(tmp_path, monkeypatch):
    """A KeyboardInterrupt mid-decompression cleans up like ZIP and TAR do."""
    gz_path = _make_gzip(tmp_path / f"{MEMBER}.gz")
    outdir = tmp_path / "output"
    outdir.mkdir()
    (outdir / MEMBER).write_bytes(PREVIOUS)

    monkeypatch.setattr(
        archives.gzip, "open", lambda *args, **kwargs: _InterruptedReader()
    )

    with pytest.raises(KeyboardInterrupt):
        utils.p_f_gunzip(gz_path, outdir=outdir, overwrite=True)

    assert (outdir / MEMBER).read_bytes() == PREVIOUS
    assert _leftovers(outdir, MEMBER) == []


@pytest.mark.parametrize("existing", [None, PREVIOUS], ids=["fresh", "existing"])
def test_empty_gzip_file_is_rejected(tmp_path, existing):
    """An empty .gz file is not valid GZIP and must not publish an empty output.

    ZIP and TAR raise for an empty file too (BadZipFile and ReadError).
    """
    gz_path = tmp_path / f"{MEMBER}.gz"
    gz_path.write_bytes(b"")
    outdir = tmp_path / "output"
    outdir.mkdir()
    if existing is not None:
        (outdir / MEMBER).write_bytes(existing)

    with pytest.raises(gzip.BadGzipFile):
        utils.p_f_gunzip(gz_path, outdir=outdir)

    if existing is None:
        assert not (outdir / MEMBER).exists()
    else:
        assert (outdir / MEMBER).read_bytes() == existing
    assert _leftovers(outdir, MEMBER) == []


@pytest.mark.parametrize("name", [".gz", ".GZ", "..gz", "...gz"])
def test_gzip_without_an_output_name_is_rejected(tmp_path, name):
    """A name with nothing before ``.gz`` has no output name to derive.

    The output used to be ``outdir / src.stem``. For ``.gz`` that is the
    source itself, so decompressing next to the source (as the extract hook
    does) replaced the archive with its own contents. For ``..gz`` and
    ``...gz`` it is ``outdir`` or its parent.
    """
    gz_path = _make_gzip(tmp_path / name)
    compressed = gz_path.read_bytes()

    with pytest.raises(ValueError, match="output name"):
        utils.p_f_gunzip(gz_path, outdir=tmp_path)

    assert gz_path.read_bytes() == compressed
    assert _leftovers(tmp_path, name) == []


def _corrupt_crc(data: bytes) -> bytes:
    raw = bytearray(gzip.compress(data))
    raw[-8] ^= 0xFF
    return bytes(raw)


def _truncated(data: bytes) -> bytes:
    return gzip.compress(data)[:-12]


def _trailing_garbage(data: bytes) -> bytes:
    return gzip.compress(data) + b"not gzip"


def _not_gzip(data: bytes) -> bytes:
    return b"plain text, not gzip"


@pytest.mark.parametrize(
    "build",
    [_corrupt_crc, _truncated, _trailing_garbage, _not_gzip],
    ids=["bad-crc", "truncated", "trailing-garbage", "not-gzip"],
)
@pytest.mark.parametrize("overwrite", [False, True])
def test_failed_decompression_keeps_existing_output(tmp_path, build, overwrite):
    """A decompression error publishes nothing and keeps the previous output."""
    gz_path = tmp_path / f"{MEMBER}.gz"
    gz_path.write_bytes(build(ORIGINAL))
    outdir = tmp_path / "output"
    outdir.mkdir()
    (outdir / MEMBER).write_bytes(PREVIOUS)

    with pytest.raises((OSError, EOFError)):
        utils.p_f_gunzip(gz_path, outdir=outdir, overwrite=overwrite)

    assert (outdir / MEMBER).read_bytes() == PREVIOUS
    assert _leftovers(outdir, MEMBER) == []


@pytest.mark.parametrize(
    "build",
    [_corrupt_crc, _truncated, _trailing_garbage, _not_gzip],
    ids=["bad-crc", "truncated", "trailing-garbage", "not-gzip"],
)
def test_failed_decompression_publishes_nothing(tmp_path, build):
    gz_path = tmp_path / f"{MEMBER}.gz"
    gz_path.write_bytes(build(ORIGINAL))
    outdir = tmp_path / "output"

    with pytest.raises((OSError, EOFError)):
        utils.p_f_gunzip(gz_path, outdir=outdir)

    assert _leftovers(outdir) == []
