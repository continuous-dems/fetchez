#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.archives
~~~~~~~~~~~~~~~~

Utility functions for archive handling.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import shutil
import tempfile
from pathlib import Path
from typing import IO, BinaryIO, Optional, List, Protocol
import filelock


import fnmatch
import hashlib
import struct
import tarfile
import gzip
import zipfile
import zlib


logger = logging.getLogger(__name__)


# =============================================================================
# Archives and extraction
# =============================================================================


def _extract_lock_path(
    src_file: Path,
    outdir: Path,
) -> Path:
    """Return a stable lock path for an archive/output pair."""
    key = hashlib.sha256(
        f"{src_file.resolve()}::{outdir.resolve()}".encode("utf-8")
    ).hexdigest()[:16]
    return outdir / f".{src_file.name}.{key}.extract.lock"


_COPY_CHUNK_SIZE = 1024 * 1024


class _Readable(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...


class UnsafeArchiveError(ValueError):
    """An archive was rejected by a safety check before anything was published.

    Raised for path traversal, colliding member paths, and exceeded size or
    member-count limits. It subclasses ValueError, which these checks raised
    before, so existing ``except ValueError`` handlers keep working.
    """


def _safe_member_path(
    root: Path,
    member_name: str,
) -> Path:
    """Resolve an archive member beneath root, rejecting path traversal.

    The member's parent directory is resolved, so an existing symlinked
    directory is followed and must stay inside root. The final component is
    not followed: an existing symlink at the member's own path is replaced on
    publication, never written through.
    """
    member = Path(member_name.replace("\\", "/"))

    if member.is_absolute():
        raise UnsafeArchiveError(f"Archive member has an absolute path: {member_name}")

    if member.name in ("", ".", ".."):
        raise UnsafeArchiveError(f"Archive member is not a file path: {member_name}")

    target = (root / member).parent.resolve() / member.name
    root_resolved = root.resolve()

    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafeArchiveError(
            f"Archive member escapes extraction directory: {member_name}"
        ) from exc

    return target


def _claim_staging_path(
    temp_path: Path,
    member_name: str,
) -> BinaryIO:
    """Create and open a member's staging file, failing if it already exists.

    Every selected member claims its staging path, even one whose existing
    output is reused, so the staging directory detects two members that map
    to the same output. That covers exact duplicates, names that normalise to
    the same path (``a//b``, ``a\\b``), a file and a directory of the same
    name, and case-only or Unicode-normalisation collisions on filesystems
    that fold them. The staging directory lives inside outdir, so it folds
    names the same way the destination does.
    """
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        return temp_path.open("xb")
    except (FileExistsError, IsADirectoryError, NotADirectoryError) as exc:
        raise UnsafeArchiveError(
            f"Archive member collides with another member's output path: {member_name}"
        ) from exc


def _check_member_limits(
    sizes: List[int],
    max_members: Optional[int],
    max_total_size: Optional[int],
) -> None:
    """Fail fast on the member count and the declared sizes.

    Declared sizes are only used to reject early. The authoritative size
    check counts decompressed bytes while copying, see _copy_limited().
    """
    if max_members is not None and len(sizes) > max_members:
        raise UnsafeArchiveError(
            f"Archive has {len(sizes)} members to extract, above the limit of "
            f"{max_members}"
        )

    if max_total_size is not None and sum(sizes) > max_total_size:
        raise UnsafeArchiveError(
            f"Archive declares {sum(sizes)} uncompressed bytes, above the limit of "
            f"{max_total_size}"
        )


def _add_to_total(
    total: int,
    size: int,
    max_total_size: Optional[int],
) -> int:
    """Return total + size, raising if that exceeds max_total_size."""
    total += size
    if max_total_size is not None and total > max_total_size:
        raise UnsafeArchiveError(
            f"Archive output exceeds the uncompressed size limit of {max_total_size} "
            "bytes"
        )
    return total


def _copy_limited(
    source: _Readable,
    target: IO[bytes],
    total: int,
    max_total_size: Optional[int],
) -> int:
    """Copy source to target, counting the decompressed bytes actually read.

    Returns the new running total. Raises before writing a chunk that would
    take the total past max_total_size, whatever the archive headers claim.
    """
    for chunk in iter(lambda: source.read(_COPY_CHUNK_SIZE), b""):
        total = _add_to_total(total, len(chunk), max_total_size)
        target.write(chunk)
    return total


def _member_matches(
    member_name: str,
    patterns: Optional[List[str]],
) -> bool:
    """Return True when an archive member matches one of the requested patterns."""
    if not patterns:
        return True

    basename = Path(member_name).name

    return any(
        pattern in basename
        or fnmatch.fnmatch(basename, pattern)
        or fnmatch.fnmatch(member_name, pattern)
        for pattern in patterns
    )


def _publish_extracted_file(
    temp_path: Path,
    dest_path: Path,
) -> None:
    """Atomically publish one extracted file.

    dest_path comes from _safe_member_path(), so its parent was already
    resolved. If the parent no longer resolves to itself, a directory on the
    way was swapped for a symlink after the member was checked, so publishing
    is refused. This narrows that race; it cannot close it without
    descriptor-relative (openat-style) extraction.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.parent.resolve() != dest_path.parent:
        raise UnsafeArchiveError(
            f"Extraction directory changed during extraction: {dest_path.parent}"
        )

    os.replace(temp_path, dest_path)


def _file_crc32(path: Path) -> int:
    """Return the CRC32 of a file, read in chunks."""
    crc = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
    return crc


def _existing_output_matches(
    path: Path,
    expected_size: int,
    expected_crc: Optional[int] = None,
) -> bool:
    """Return whether an existing output can be reused for an archive member.

    The file must be a regular file, not a symlink, of the expected size.
    When the archive records a CRC32 for the member, the file's CRC32 must
    match it too.
    """
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != expected_size
        ):
            return False

        return expected_crc is None or _file_crc32(path) == expected_crc

    except OSError:
        return False


def _gzip_output_matches(
    src_file: Path,
    dest_path: Path,
) -> bool:
    """Return whether dest_path matches the CRC32 and size in a GZIP trailer.

    The trailer stores the size modulo 2**32. For a multi-member GZIP file it
    describes only the last member, so the check fails and the file is
    decompressed again rather than wrongly reused.
    """
    try:
        if dest_path.is_symlink() or not dest_path.is_file():
            return False

        with src_file.open("rb") as handle:
            handle.seek(-8, os.SEEK_END)
            expected_crc, expected_size_mod = struct.unpack("<II", handle.read(8))

        if dest_path.stat().st_size % 2**32 != expected_size_mod:
            return False

        return _file_crc32(dest_path) == expected_crc

    except (OSError, struct.error):
        return False


def _extract_zip(
    archive: zipfile.ZipFile,
    outdir: Path,
    members: Optional[List[str]],
    overwrite: bool,
    max_members: Optional[int] = None,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Extract selected ZIP members into a staging directory."""
    result: List[Path] = []
    staged: List[tuple[Path, Path]] = []
    total = 0

    selected = [
        info
        for info in archive.infolist()
        if not info.is_dir() and _member_matches(info.filename, members)
    ]
    _check_member_limits(
        [info.file_size for info in selected], max_members, max_total_size
    )

    with tempfile.TemporaryDirectory(
        prefix=f".{outdir.name}.extract-",
        dir=outdir,
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        for info in selected:
            temp_path = _safe_member_path(temp_dir, info.filename)
            dest_path = _safe_member_path(outdir, info.filename)

            with _claim_staging_path(temp_path, info.filename) as target:
                result.append(dest_path)

                if not overwrite and _existing_output_matches(
                    dest_path, info.file_size, info.CRC
                ):
                    total = _add_to_total(total, info.file_size, max_total_size)
                    continue

                with archive.open(info, "r") as source:
                    total = _copy_limited(source, target, total, max_total_size)

            staged.append((temp_path, dest_path))

        for temp_path, dest_path in staged:
            _publish_extracted_file(temp_path, dest_path)

    return result


def _extract_tar(
    archive: tarfile.TarFile,
    outdir: Path,
    members: Optional[List[str]],
    overwrite: bool,
    max_members: Optional[int] = None,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Extract selected regular TAR members into a staging directory."""
    result: List[Path] = []
    staged: List[tuple[Path, Path]] = []
    total = 0

    selected = [
        info
        for info in archive.getmembers()
        if info.isfile() and _member_matches(info.name, members)
    ]
    _check_member_limits([info.size for info in selected], max_members, max_total_size)

    with tempfile.TemporaryDirectory(
        prefix=f".{outdir.name}.extract-",
        dir=outdir,
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        for info in selected:
            temp_path = _safe_member_path(temp_dir, info.name)
            dest_path = _safe_member_path(outdir, info.name)

            with _claim_staging_path(temp_path, info.name) as target:
                # TAR headers carry no checksum of the member contents, so an
                # existing file is matched on size alone.
                if not overwrite and _existing_output_matches(dest_path, info.size):
                    result.append(dest_path)
                    total = _add_to_total(total, info.size, max_total_size)
                    continue

                source = archive.extractfile(info)
                if source is None:
                    continue

                result.append(dest_path)

                with source:
                    total = _copy_limited(source, target, total, max_total_size)

            staged.append((temp_path, dest_path))

        for temp_path, dest_path in staged:
            _publish_extracted_file(temp_path, dest_path)

    return result


def _extract_gzip(
    src_file: Path,
    outdir: Path,
    overwrite: bool,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Decompress one GZIP file and atomically publish its output.

    GZIP has no trustworthy uncompressed size up front (the trailer holds it
    modulo 2**32, for the last member only), so max_total_size is enforced
    only on the bytes actually decompressed.
    """
    dest_path = outdir / src_file.stem
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if not overwrite and _gzip_output_matches(src_file, dest_path):
        _add_to_total(0, dest_path.stat().st_size, max_total_size)
        return [dest_path]

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{dest_path.name}.",
        suffix=".tmp",
        dir=dest_path.parent,
    )

    try:
        with os.fdopen(fd, "wb") as target:
            with gzip.open(src_file, "rb") as source:
                _copy_limited(source, target, 0, max_total_size)

            target.flush()
            os.fsync(target.fileno())

        os.replace(temp_name, dest_path)

    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise

    return [dest_path]


def p_f_extract(
    src_file: str | Path,
    outdir: str | Path = "./",
    members: Optional[List[str]] = None,
    overwrite: bool = False,
    *,
    max_members: Optional[int] = None,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Safely extract or decompress an archive.

    Supports ZIP, TAR, TAR.GZ, TGZ, and GZ archives.

    ZIP and TAR members are staged in a temporary directory before being
    atomically published into the destination directory. GZ files are
    decompressed to a temporary file before atomic publication.

    Extraction is serialized per source/output pair using an inter-process
    file lock.

    With ``overwrite=True`` every selected member is extracted again and
    replaces any existing output.

    With ``overwrite=False`` an existing output is reused only when it is a
    regular file that passes the cheapest check the format allows; otherwise
    it is extracted again and replaced:

    - ZIP: size and CRC32 match the member's central-directory entry.
    - GZIP: size (modulo 2**32) and CRC32 match the GZIP trailer.
    - TAR, TAR.GZ, TGZ: size matches the member header. TAR records no
      checksum of member contents, so a same-size file with different
      contents is reused. Use ``overwrite=True`` to force a refresh.

    The ZIP and GZIP checks read the existing output once to compute its
    CRC32, which is much cheaper than decompressing and rewriting it.

    Safety rules. Each raises :class:`UnsafeArchiveError` (a ValueError)
    before any output is published:

    - A member with an absolute path, or one that resolves outside
      ``outdir``, is rejected. Existing directories inside ``outdir`` are
      resolved, so a symlinked directory that points outside is rejected too.
    - A member's own output path is never followed. An existing symlink there
      is never reused and is replaced by the extracted file, so the write
      cannot land elsewhere.
    - Only regular files are extracted. TAR symlinks, hard links, devices and
      FIFOs are skipped, and ZIP entries are always written as regular files.
    - When two selected members map to the same output path, the archive is
      rejected. This covers duplicate names, names that normalise to the same
      path, and a file and a directory with the same name. It also covers
      case-only (and Unicode normalisation) collisions, but only where the
      destination filesystem folds them; on a case-sensitive filesystem
      ``A.txt`` and ``a.txt`` are two different outputs.
    - ``max_members`` and ``max_total_size`` are optional limits for
      untrusted archives. Both default to None, meaning no limit. The member
      count and the declared sizes are checked up front, and the size limit
      is also enforced on the bytes actually decompressed, so an archive
      whose headers understate its size still fails. Reused outputs count
      towards ``max_total_size``, so the result does not depend on what is
      already on disk. For GZIP only ``max_total_size`` applies.

    Args:
        src_file: Archive or compressed file.
        outdir: Directory where extracted files should be published.
        members: Optional filename/pattern filters. Matching is performed
            against both the member path and basename. When None, all regular
            archive members are extracted.
        overwrite: Always re-extract and replace existing output files.
        max_members: Optional maximum number of selected members.
        max_total_size: Optional maximum total uncompressed size, in bytes,
            of the selected outputs.

    Returns:
        List of extracted or reused output paths.

    Raises:
        UnsafeArchiveError: The archive failed one of the safety rules above.
        ValueError: The archive format is not supported.
    """
    src_file = Path(src_file)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    suffix = src_file.name.casefold()

    # GZIP is special because .tar.gz must be treated as a TAR archive.
    if suffix.endswith((".tar.gz", ".tgz")):
        archive_type = "tar"
    elif suffix.endswith(".tar"):
        archive_type = "tar"
    elif suffix.endswith(".zip"):
        archive_type = "zip"
    elif suffix.endswith(".gz"):
        archive_type = "gzip"
    else:
        raise ValueError(f"Unsupported archive format: {src_file}")

    lock_path = _extract_lock_path(src_file, outdir)

    with filelock.FileLock(str(lock_path), timeout=3600):
        if archive_type == "gzip":
            return _extract_gzip(
                src_file,
                outdir,
                overwrite,
                max_total_size,
            )

        if archive_type == "zip":
            with zipfile.ZipFile(src_file, "r") as archive:
                return _extract_zip(
                    archive,
                    outdir,
                    members,
                    overwrite,
                    max_members,
                    max_total_size,
                )

        with tarfile.open(src_file, "r:*") as archive:
            return _extract_tar(
                archive,
                outdir,
                members,
                overwrite,
                max_members,
                max_total_size,
            )


def p_f_unzip(
    src_file: str | Path,
    fns: Optional[List[str]] = None,
    outdir: str | Path = "./",
    overwrite: bool = False,
    *,
    max_members: Optional[int] = None,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Compatibility wrapper for extracting ZIP files."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        members=fns,
        overwrite=overwrite,
        max_members=max_members,
        max_total_size=max_total_size,
    )


def p_f_untar(
    src_file: str | Path,
    fns: Optional[List[str]] = None,
    outdir: str | Path = "./",
    overwrite: bool = False,
    *,
    max_members: Optional[int] = None,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Extract selected TAR archive members."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        members=fns,
        overwrite=overwrite,
        max_members=max_members,
        max_total_size=max_total_size,
    )


def p_f_gunzip(
    src_file: str | Path,
    outdir: str | Path = "./",
    overwrite: bool = False,
    *,
    max_total_size: Optional[int] = None,
) -> List[Path]:
    """Decompress one GZIP file."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        overwrite=overwrite,
        max_total_size=max_total_size,
    )


def p_unzip(src_fn: str, ext: list, outdir: str = ".", verbose: bool = False) -> list:
    """Unzip specific extensions from a zip file, flattening directory structures.

    Every matching member is written to ``outdir / <basename>``, so the
    member's directories are dropped. Backslashes count as separators, as
    in p_f_extract(). Each file is written to a temporary file and moved into
    place with os.replace(). An existing symlink at the target is therefore
    replaced, never written through.

    When two members flatten to the same output file (same basename, or a
    case-only difference on a case-insensitive filesystem), the later member
    wins, as it did before. A warning is logged and the path is listed once.

    Errors are logged rather than raised, and the files written before the
    error are returned.

    Args:
        src_fn: Path to the source zip file.
        ext: List of extensions to extract (e.g., ['shp', 'shx', 'dbf']).
        outdir: Directory to extract files into.
        verbose: Print debug info.

    Returns:
        List of paths to the extracted files.
    """
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)

    extracted_files: List[str] = []
    # (st_dev, st_ino) of each file published by this call -> its listed path.
    published: dict[tuple[int, int], str] = {}

    try:
        with zipfile.ZipFile(src_fn, "r") as z:
            want_exts = [
                e.lower() if e.startswith(".") else f".{e.lower()}" for e in ext
            ]

            for file_info in z.infolist():
                if file_info.is_dir():
                    continue

                file_path = Path(file_info.filename.replace("\\", "/"))
                f_ext = file_path.suffix
                if f_ext.lower() in want_exts:
                    filename = file_path.name
                    target_path = outdir_path / filename

                    if verbose:
                        logger.info(f"Extracting {filename}...")

                    fd, temp_name = tempfile.mkstemp(
                        prefix=f".{filename}.", suffix=".tmp", dir=outdir_path
                    )
                    try:
                        with os.fdopen(fd, "wb") as target, z.open(file_info) as source:
                            shutil.copyfileobj(source, target)

                        try:
                            existing = target_path.lstat()
                            previous = published.pop(
                                (existing.st_dev, existing.st_ino), None
                            )
                        except FileNotFoundError:
                            previous = None

                        os.replace(temp_name, target_path)

                    except BaseException:
                        Path(temp_name).unlink(missing_ok=True)
                        raise

                    if previous is not None:
                        logger.warning(
                            "%s: member %s replaces an earlier member flattened to %s",
                            src_fn,
                            file_info.filename,
                            previous,
                        )
                        extracted_files.remove(previous)

                    new = target_path.lstat()
                    published[(new.st_dev, new.st_ino)] = str(target_path)
                    extracted_files.append(str(target_path))

    except zipfile.BadZipFile:
        logger.error(f"Bad Zip File: {src_fn}")
    except Exception as e:
        logger.error(f"Unzip error {src_fn}: {e}")

    return extracted_files
