# tests/utils/test_utils_extract_safety.py

"""Archive validation and security for fetchez.utils.archives (issue #530, section 3).

Every archive, including the malicious ones, is built with zipfile, tarfile
and gzip inside pytest's ``tmp_path``. Nothing touches the network.
"""

import gzip
import io
import logging
import os
import stat
import tarfile
import warnings
import zipfile
from pathlib import Path

import pytest

from fetchez import utils
from fetchez.hooks.extract import Extract
from fetchez.utils import archives

ARCHIVE_KINDS = ["zip", "tar", "tar.gz"]


def _make_archive(path: Path, kind: str, entries: list[tuple[str, bytes]]) -> Path:
    """Write entries in order, keeping duplicate and unusual names as given."""
    if kind == "zip":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile warns on duplicate names
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, data in entries:
                    zf.writestr(zipfile.ZipInfo(name), data)
        return path

    with tarfile.open(path, "w:gz" if kind == "tar.gz" else "w") as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def _archive(tmp_path: Path, kind: str, entries: list[tuple[str, bytes]]) -> Path:
    return _make_archive(tmp_path / f"input.{kind}", kind, entries)


def _outdir(tmp_path: Path) -> Path:
    outdir = tmp_path / "output"
    outdir.mkdir()
    return outdir


def _published(outdir: Path) -> list[str]:
    """Files under outdir, ignoring the lock file. Staging dirs would show up."""
    return sorted(
        str(p.relative_to(outdir))
        for p in outdir.rglob("*")
        if not p.name.endswith(".extract.lock") and not p.is_dir()
    )


def _symlink(link: Path, target: Path | str) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")


def _fs_folds_case(directory: Path) -> bool:
    probe = directory / "case-probe"
    probe.touch()
    try:
        return (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


# ---------------------------------------------------------------------------
# Traversal and symlinks through existing filesystem entries
# ---------------------------------------------------------------------------


def test_unsafe_archive_error_is_a_value_error():
    assert issubclass(utils.UnsafeArchiveError, ValueError)


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "a/../../evil.txt", "..\\evil.txt", "/abs/evil.txt", "x/.."],
)
def test_traversal_and_absolute_members_are_rejected(tmp_path, kind, name):
    archive = _archive(tmp_path, kind, [("ok.txt", b"ok"), (name, b"evil")])
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir)

    assert _published(outdir) == []
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_symlinked_directory_pointing_outside_is_rejected(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("link/evil.txt", b"evil")])
    outdir = _outdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink(outdir / "link", outside)

    with pytest.raises(ValueError):
        utils.p_f_extract(archive, outdir)

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_symlinked_directory_inside_outdir_is_followed(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("alias/data.txt", b"data")])
    outdir = _outdir(tmp_path)
    (outdir / "real").mkdir()
    _symlink(outdir / "alias", "real")

    result = utils.p_f_extract(archive, outdir)

    assert result == [outdir.resolve() / "real" / "data.txt"]
    assert (outdir / "real" / "data.txt").read_bytes() == b"data"


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
@pytest.mark.parametrize("victim_data", [b"precious", b"new"], ids=["other", "same"])
def test_symlink_at_member_path_pointing_outside_is_replaced(
    tmp_path, kind, victim_data
):
    archive = _archive(tmp_path, kind, [("a.txt", b"new")])
    outdir = _outdir(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_bytes(victim_data)
    _symlink(outdir / "a.txt", victim)

    result = utils.p_f_extract(archive, outdir, overwrite=False)

    assert result == [outdir.resolve() / "a.txt"]
    assert not (outdir / "a.txt").is_symlink()
    assert (outdir / "a.txt").read_bytes() == b"new"
    assert victim.read_bytes() == victim_data


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
@pytest.mark.parametrize("other_data", [b"precious", b"new"], ids=["other", "same"])
def test_symlink_at_member_path_inside_is_replaced_not_written_through(
    tmp_path, kind, other_data
):
    # With "same" contents the old code reused the symlink's target.
    archive = _archive(tmp_path, kind, [("a.txt", b"new")])
    outdir = _outdir(tmp_path)
    (outdir / "b.txt").write_bytes(other_data)
    _symlink(outdir / "a.txt", "b.txt")

    result = utils.p_f_extract(archive, outdir, overwrite=False)

    assert result == [outdir.resolve() / "a.txt"]
    assert not (outdir / "a.txt").is_symlink()
    assert (outdir / "a.txt").read_bytes() == b"new"
    assert (outdir / "b.txt").read_bytes() == other_data


def test_tar_link_and_special_members_are_not_created(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = tmp_path / "input.tar"

    with tarfile.open(archive, "w") as tf:
        sym = tarfile.TarInfo("link")
        sym.type = tarfile.SYMTYPE
        sym.linkname = str(outside)
        tf.addfile(sym)

        hard = tarfile.TarInfo("hard.txt")
        hard.type = tarfile.LNKTYPE
        hard.linkname = str(outside / "target.txt")
        tf.addfile(hard)

        fifo = tarfile.TarInfo("pipe")
        fifo.type = tarfile.FIFOTYPE
        tf.addfile(fifo)

        data = b"through the link?"
        info = tarfile.TarInfo("link/file.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    outdir = _outdir(tmp_path)
    result = utils.p_f_extract(archive, outdir)

    assert result == [outdir.resolve() / "link" / "file.txt"]
    assert (outdir / "link").is_dir() and not (outdir / "link").is_symlink()
    assert not (outdir / "hard.txt").exists()
    assert not (outdir / "pipe").exists()
    assert list(outside.iterdir()) == []


def test_zip_symlink_entry_is_written_as_regular_file(tmp_path):
    archive = tmp_path / "input.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3  # Unix, so external_attr carries the mode
    info.external_attr = (stat.S_IFLNK | 0o777) << 16

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, str(tmp_path))

    outdir = _outdir(tmp_path)
    utils.p_f_extract(archive, outdir)

    assert not (outdir / "link").is_symlink()
    assert (outdir / "link").read_bytes() == str(tmp_path).encode()


def test_publish_refuses_directory_swapped_for_symlink(tmp_path, monkeypatch):
    archive = _archive(tmp_path, "zip", [("sub/data.txt", b"data")])
    outdir = _outdir(tmp_path)
    (outdir / "sub").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    original = archives._copy_limited

    def copy_then_swap(*args, **kwargs):
        # Simulate another process replacing a checked directory with a
        # symlink between the path check and publication.
        total = original(*args, **kwargs)
        (outdir / "sub").rename(tmp_path / "moved-sub")
        (outdir / "sub").symlink_to(outside)
        return total

    monkeypatch.setattr(archives, "_copy_limited", copy_then_swap)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir)

    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------------------
# Duplicate member names and output-path collisions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
@pytest.mark.parametrize(
    "second",
    ["dir/a.txt", "dir//a.txt", "dir/./a.txt", "dir\\a.txt", "x/../dir/a.txt"],
)
def test_members_mapping_to_one_output_are_rejected(tmp_path, kind, second):
    archive = _archive(
        tmp_path,
        kind,
        [("first.txt", b"first"), ("dir/a.txt", b"one"), (second, b"two")],
    )
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError, match="collides"):
        utils.p_f_extract(archive, outdir)

    # Rejected before publication: not even the unrelated member appears.
    assert _published(outdir) == []


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
@pytest.mark.parametrize(
    "order", [("f", "f/g"), ("f/g", "f")], ids=["file-first", "dir-first"]
)
def test_file_and_directory_with_same_name_are_rejected(tmp_path, kind, order):
    archive = _archive(tmp_path, kind, [(name, b"x") for name in order])
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError, match="collides"):
        utils.p_f_extract(archive, outdir)

    assert _published(outdir) == []


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_duplicate_is_rejected_even_when_first_copy_is_reused(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("d.txt", b"one"), ("d.txt", b"TWO")])
    outdir = _outdir(tmp_path)
    (outdir / "d.txt").write_bytes(b"one")

    with pytest.raises(utils.UnsafeArchiveError, match="collides"):
        utils.p_f_extract(archive, outdir, overwrite=False)

    assert (outdir / "d.txt").read_bytes() == b"one"


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_case_only_names_follow_the_destination_filesystem(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("Data.txt", b"upper"), ("data.txt", b"lower")])
    outdir = _outdir(tmp_path)

    if _fs_folds_case(outdir):
        with pytest.raises(utils.UnsafeArchiveError, match="collides"):
            utils.p_f_extract(archive, outdir)
        assert _published(outdir) == []
    else:
        result = utils.p_f_extract(archive, outdir)
        assert [p.name for p in result] == ["Data.txt", "data.txt"]
        assert (outdir / "Data.txt").read_bytes() == b"upper"
        assert (outdir / "data.txt").read_bytes() == b"lower"


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_duplicates_outside_the_member_filter_are_ignored(tmp_path, kind):
    archive = _archive(
        tmp_path,
        kind,
        [("keep.dat", b"keep"), ("skip.txt", b"one"), ("skip.txt", b"two")],
    )
    outdir = _outdir(tmp_path)

    result = utils.p_f_extract(archive, outdir, members=["*.dat"])

    assert result == [outdir.resolve() / "keep.dat"]


# ---------------------------------------------------------------------------
# Optional limits for untrusted archives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_max_members(tmp_path, kind):
    archive = _archive(tmp_path, kind, [(f"m{i}.txt", b"x") for i in range(3)])
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError, match="members"):
        utils.p_f_extract(archive, outdir, max_members=2)
    assert _published(outdir) == []

    assert len(utils.p_f_extract(archive, outdir, max_members=3)) == 3


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_max_total_size(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("a.txt", b"x" * 600), ("b.txt", b"y" * 600)])
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir, max_total_size=1199)
    assert _published(outdir) == []

    assert len(utils.p_f_extract(archive, outdir, max_total_size=1200)) == 2


def test_max_total_size_counts_decompressed_gzip_bytes(tmp_path):
    archive = tmp_path / "bomb.dat.gz"
    with gzip.open(archive, "wb") as handle:
        handle.write(bytes(4 * 1024 * 1024))
    assert archive.stat().st_size < 16 * 1024  # highly compressible
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir, max_total_size=1024 * 1024)

    assert _published(outdir) == []


def test_max_total_size_does_not_trust_the_gzip_trailer(tmp_path):
    # Two GZIP members: the trailer describes only the tiny last one.
    archive = tmp_path / "multi.dat.gz"
    archive.write_bytes(gzip.compress(bytes(2 * 1024 * 1024)) + gzip.compress(b"tiny"))
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir, max_total_size=1024)

    assert _published(outdir) == []


@pytest.mark.parametrize("kind", ARCHIVE_KINDS)
def test_reused_outputs_count_towards_max_total_size(tmp_path, kind):
    archive = _archive(tmp_path, kind, [("a.txt", b"x" * 100)])
    outdir = _outdir(tmp_path)
    utils.p_f_extract(archive, outdir)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir, overwrite=False, max_total_size=99)


def test_reused_gzip_output_counts_towards_max_total_size(tmp_path):
    archive = tmp_path / "a.dat.gz"
    archive.write_bytes(gzip.compress(b"x" * 100))
    outdir = _outdir(tmp_path)
    utils.p_f_extract(archive, outdir)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_extract(archive, outdir, overwrite=False, max_total_size=99)


def test_wrappers_forward_limits(tmp_path):
    zip_path = _archive(tmp_path, "zip", [("a.txt", b"x" * 10), ("b.txt", b"y")])
    tar_path = _archive(tmp_path, "tar", [("a.txt", b"x" * 10), ("b.txt", b"y")])
    gz_path = tmp_path / "c.dat.gz"
    gz_path.write_bytes(gzip.compress(b"z" * 10))
    outdir = _outdir(tmp_path)

    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_unzip(zip_path, outdir=outdir, max_members=1)
    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_untar(tar_path, outdir=outdir, max_total_size=5)
    with pytest.raises(utils.UnsafeArchiveError):
        utils.p_f_gunzip(gz_path, outdir=outdir, max_total_size=5)


# ---------------------------------------------------------------------------
# Legacy p_unzip(): flattened extraction
# ---------------------------------------------------------------------------


def test_p_unzip_replaces_symlink_instead_of_writing_through(tmp_path):
    archive = _archive(tmp_path, "zip", [("dir/x.shp", b"new")])
    outdir = _outdir(tmp_path)
    victim = tmp_path / "victim.shp"
    victim.write_bytes(b"precious")
    _symlink(outdir / "x.shp", victim)

    result = utils.p_unzip(str(archive), ["shp"], outdir=str(outdir))

    assert result == [str(outdir / "x.shp")]
    assert not (outdir / "x.shp").is_symlink()
    assert (outdir / "x.shp").read_bytes() == b"new"
    assert victim.read_bytes() == b"precious"


def test_p_unzip_basename_collision_keeps_last_and_lists_once(tmp_path, caplog):
    archive = _archive(
        tmp_path,
        "zip",
        [("d1/x.shp", b"one"), ("d1/x.dbf", b"dbf"), ("d2/x.shp", b"two")],
    )
    outdir = _outdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger="fetchez.utils.archives"):
        result = utils.p_unzip(str(archive), ["shp", "dbf"], outdir=str(outdir))

    assert result == [str(outdir / "x.dbf"), str(outdir / "x.shp")]
    assert (outdir / "x.shp").read_bytes() == b"two"
    assert "d2/x.shp" in caplog.text


def test_p_unzip_case_only_names_follow_the_destination_filesystem(tmp_path):
    archive = _archive(tmp_path, "zip", [("a/X.shp", b"upper"), ("b/x.shp", b"lower")])
    outdir = _outdir(tmp_path)

    result = utils.p_unzip(str(archive), ["shp"], outdir=str(outdir))

    if _fs_folds_case(outdir):
        assert result == [str(outdir / "x.shp")]
        assert (outdir / "x.shp").read_bytes() == b"lower"
    else:
        assert result == [str(outdir / "X.shp"), str(outdir / "x.shp")]


def test_p_unzip_treats_backslash_as_separator(tmp_path):
    archive = _archive(tmp_path, "zip", [("dir\\sub\\x.shp", b"data")])
    outdir = _outdir(tmp_path)

    result = utils.p_unzip(str(archive), ["shp"], outdir=str(outdir))

    assert result == [str(outdir / "x.shp")]
    assert os.listdir(outdir) == ["x.shp"]


def test_p_unzip_failed_member_keeps_existing_file_and_leaves_no_temp(tmp_path):
    archive = _archive(tmp_path, "zip", [("x.shp", b"A" * 64)])
    # Corrupt the stored data so the CRC check fails at the end of the read.
    raw = bytearray(archive.read_bytes())
    with zipfile.ZipFile(archive) as zf:
        info = zf.getinfo("x.shp")
        offset = info.header_offset + 30 + len(info.filename.encode())
    raw[offset] ^= 0xFF
    archive.write_bytes(bytes(raw))

    outdir = _outdir(tmp_path)
    (outdir / "x.shp").write_bytes(b"previous")

    assert utils.p_unzip(str(archive), ["shp"], outdir=str(outdir)) == []
    assert (outdir / "x.shp").read_bytes() == b"previous"
    assert os.listdir(outdir) == ["x.shp"]


# ---------------------------------------------------------------------------
# Extract hook
# ---------------------------------------------------------------------------


def test_extract_hook_reports_unsafe_archive(tmp_path, caplog):
    archive = _archive(tmp_path, "zip", [("../evil.txt", b"evil")])
    entry = {"dst_fn": str(archive), "status": 0}

    with caplog.at_level(logging.ERROR, logger="fetchez.hooks.extract"):
        out = Extract().run([(None, entry)])

    assert out == [(None, entry)]
    assert "Refusing to extract" in caplog.text
    assert not (tmp_path / "evil.txt").exists()
