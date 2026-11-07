# tests/utils/test_utils_extract_overwrite.py

"""Overwrite and reuse rules for fetchez.utils.archives (issue #530, section 1).

Every archive is built inside pytest's ``tmp_path``. A reused output keeps its
inode; a re-extracted output is published with ``os.replace()`` and gets a new
one, which is how these tests tell the two apart.
"""

import gzip
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from fetchez import utils

MEMBER = "resource.dat"
ORIGINAL = b"original data"
SAME_SIZE_STALE = b"stale-content"  # same length as ORIGINAL, different bytes
SHORTER_STALE = b"stale"

assert len(SAME_SIZE_STALE) == len(ORIGINAL)


def _make_zip(path: Path, data: bytes = ORIGINAL) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MEMBER, data)
    return path


def _make_tar(path: Path, data: bytes = ORIGINAL) -> Path:
    mode = "w:gz" if path.name.endswith((".tar.gz", ".tgz")) else "w"
    with tarfile.open(path, mode) as archive:
        info = tarfile.TarInfo(MEMBER)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return path


def _make_gzip(path: Path, data: bytes = ORIGINAL) -> Path:
    with gzip.open(path, "wb") as target:
        target.write(data)
    return path


def _output_path(archive_path: Path, outdir: Path) -> Path:
    if archive_path.name.endswith(".gz") and not archive_path.name.endswith(".tar.gz"):
        return outdir / archive_path.stem
    return outdir / MEMBER


ARCHIVES = [
    pytest.param("input.zip", _make_zip, id="zip"),
    pytest.param("input.tar", _make_tar, id="tar"),
    pytest.param("input.tar.gz", _make_tar, id="tar.gz"),
    pytest.param(f"{MEMBER}.gz", _make_gzip, id="gzip"),
]

# Archive types that carry a CRC32 for the member, so a same-size file with
# different contents is detected without overwrite=True.
CHECKSUMMED = [
    pytest.param("input.zip", _make_zip, id="zip"),
    pytest.param(f"{MEMBER}.gz", _make_gzip, id="gzip"),
]

TAR_ONLY = [
    pytest.param("input.tar", _make_tar, id="tar"),
    pytest.param("input.tar.gz", _make_tar, id="tar.gz"),
]


def _setup(tmp_path: Path, name: str, make, existing: bytes | None) -> tuple:
    archive_path = make(tmp_path / name)
    outdir = tmp_path / "output"
    outdir.mkdir()
    out_path = _output_path(archive_path, outdir)
    if existing is not None:
        out_path.write_bytes(existing)
    return archive_path, outdir, out_path


@pytest.mark.parametrize("name, make", ARCHIVES)
def test_overwrite_true_replaces_same_size_existing_file(tmp_path, name, make):
    archive_path, outdir, out_path = _setup(tmp_path, name, make, SAME_SIZE_STALE)

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=True)

    assert result == [out_path]
    assert out_path.read_bytes() == ORIGINAL


@pytest.mark.parametrize("name, make", ARCHIVES)
def test_overwrite_true_re_extracts_valid_existing_file(tmp_path, name, make):
    archive_path, outdir, out_path = _setup(tmp_path, name, make, None)
    utils.p_f_extract(archive_path, outdir=outdir)
    first_inode = out_path.stat().st_ino

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=True)

    assert result == [out_path]
    assert out_path.read_bytes() == ORIGINAL
    assert out_path.stat().st_ino != first_inode


@pytest.mark.parametrize("name, make", ARCHIVES)
def test_overwrite_false_reuses_valid_existing_file(tmp_path, name, make):
    archive_path, outdir, out_path = _setup(tmp_path, name, make, None)
    utils.p_f_extract(archive_path, outdir=outdir)
    first_inode = out_path.stat().st_ino

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [out_path]
    assert out_path.read_bytes() == ORIGINAL
    assert out_path.stat().st_ino == first_inode


@pytest.mark.parametrize("name, make", ARCHIVES)
def test_overwrite_false_replaces_existing_file_of_wrong_size(tmp_path, name, make):
    archive_path, outdir, out_path = _setup(tmp_path, name, make, SHORTER_STALE)

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [out_path]
    assert out_path.read_bytes() == ORIGINAL


@pytest.mark.parametrize("name, make", CHECKSUMMED)
def test_overwrite_false_replaces_same_size_file_with_wrong_crc(tmp_path, name, make):
    archive_path, outdir, out_path = _setup(tmp_path, name, make, SAME_SIZE_STALE)

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [out_path]
    assert out_path.read_bytes() == ORIGINAL


@pytest.mark.parametrize("name, make", TAR_ONLY)
def test_overwrite_false_tar_matches_on_size_only(tmp_path, name, make):
    """TAR headers carry no content checksum, so a same-size file is reused.

    This pins the documented TAR rule; pass overwrite=True to force a refresh.
    """
    archive_path, outdir, out_path = _setup(tmp_path, name, make, SAME_SIZE_STALE)

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [out_path]
    assert out_path.read_bytes() == SAME_SIZE_STALE


def test_overwrite_false_replaces_partial_zip_members_only(tmp_path):
    """Valid members are reused and invalid ones re-extracted in the same call."""
    archive_path = tmp_path / "input.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("good.dat", ORIGINAL)
        archive.writestr("bad.dat", ORIGINAL)

    outdir = tmp_path / "output"
    outdir.mkdir()
    utils.p_f_extract(archive_path, outdir=outdir)
    good_inode = (outdir / "good.dat").stat().st_ino
    (outdir / "bad.dat").write_bytes(SAME_SIZE_STALE)

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [outdir / "good.dat", outdir / "bad.dat"]
    assert (outdir / "good.dat").stat().st_ino == good_inode
    assert (outdir / "bad.dat").read_bytes() == ORIGINAL


@pytest.mark.parametrize("overwrite", [False, True])
def test_gzip_leaves_no_temp_files(tmp_path, overwrite):
    archive_path, outdir, out_path = _setup(
        tmp_path, f"{MEMBER}.gz", _make_gzip, SAME_SIZE_STALE
    )

    utils.p_f_extract(archive_path, outdir=outdir, overwrite=overwrite)

    assert out_path.read_bytes() == ORIGINAL
    assert not list(outdir.glob(".*.tmp"))


def test_multi_member_gzip_is_decompressed_again_not_reused(tmp_path):
    """The trailer describes only the last member, so reuse is never assumed."""
    archive_path = tmp_path / f"{MEMBER}.gz"
    archive_path.write_bytes(gzip.compress(b"first part ") + gzip.compress(ORIGINAL))
    outdir = tmp_path / "output"
    outdir.mkdir()
    out_path = outdir / MEMBER

    utils.p_f_extract(archive_path, outdir=outdir)
    first_inode = out_path.stat().st_ino

    result = utils.p_f_extract(archive_path, outdir=outdir, overwrite=False)

    assert result == [out_path]
    assert out_path.read_bytes() == b"first part " + ORIGINAL
    assert out_path.stat().st_ino != first_inode
