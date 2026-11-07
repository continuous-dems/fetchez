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
from typing import Optional, List
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


def _safe_member_path(
    root: Path,
    member_name: str,
) -> Path:
    """Resolve an archive member beneath root, rejecting path traversal."""
    member = Path(member_name.replace("\\", "/"))

    if member.is_absolute():
        raise ValueError(f"Archive member has an absolute path: {member_name}")

    target = (root / member).resolve()
    root_resolved = root.resolve()

    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Archive member escapes extraction directory: {member_name}"
        ) from exc

    return target


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
    """Atomically publish one extracted file."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
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

    The file must be a regular file of the expected size. When the archive
    records a CRC32 for the member, the file's CRC32 must match it too.
    """
    try:
        if not path.is_file() or path.stat().st_size != expected_size:
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
        if not dest_path.is_file():
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
) -> List[Path]:
    """Extract selected ZIP members into a staging directory."""
    result: List[Path] = []
    staged: List[tuple[Path, Path]] = []

    with tempfile.TemporaryDirectory(
        prefix=f".{outdir.name}.extract-",
        dir=outdir,
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        for info in archive.infolist():
            if info.is_dir() or not _member_matches(info.filename, members):
                continue

            temp_path = _safe_member_path(temp_dir, info.filename)
            dest_path = _safe_member_path(outdir, info.filename)
            result.append(dest_path)

            if not overwrite and _existing_output_matches(
                dest_path, info.file_size, info.CRC
            ):
                continue

            temp_path.parent.mkdir(parents=True, exist_ok=True)

            with archive.open(info, "r") as source, temp_path.open("wb") as target:
                shutil.copyfileobj(source, target)

            staged.append((temp_path, dest_path))

        for temp_path, dest_path in staged:
            _publish_extracted_file(temp_path, dest_path)

    return result


def _extract_tar(
    archive: tarfile.TarFile,
    outdir: Path,
    members: Optional[List[str]],
    overwrite: bool,
) -> List[Path]:
    """Extract selected regular TAR members into a staging directory."""
    result: List[Path] = []
    staged: List[tuple[Path, Path]] = []

    with tempfile.TemporaryDirectory(
        prefix=f".{outdir.name}.extract-",
        dir=outdir,
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        for info in archive.getmembers():
            if not info.isfile() or not _member_matches(info.name, members):
                continue

            temp_path = _safe_member_path(temp_dir, info.name)
            dest_path = _safe_member_path(outdir, info.name)

            # TAR headers carry no checksum of the member contents, so an
            # existing file is matched on size alone.
            if not overwrite and _existing_output_matches(dest_path, info.size):
                result.append(dest_path)
                continue

            source = archive.extractfile(info)
            if source is None:
                continue

            result.append(dest_path)
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            with source, temp_path.open("wb") as target:
                shutil.copyfileobj(source, target)

            staged.append((temp_path, dest_path))

        for temp_path, dest_path in staged:
            _publish_extracted_file(temp_path, dest_path)

    return result


def _extract_gzip(
    src_file: Path,
    outdir: Path,
    overwrite: bool,
) -> List[Path]:
    """Decompress one GZIP file and atomically publish its output."""
    dest_path = outdir / src_file.stem
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if not overwrite and _gzip_output_matches(src_file, dest_path):
        return [dest_path]

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{dest_path.name}.",
        suffix=".tmp",
        dir=dest_path.parent,
    )

    try:
        with os.fdopen(fd, "wb") as target:
            with gzip.open(src_file, "rb") as source:
                shutil.copyfileobj(source, target)

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

    Args:
        src_file: Archive or compressed file.
        outdir: Directory where extracted files should be published.
        members: Optional filename/pattern filters. Matching is performed
            against both the member path and basename. When None, all regular
            archive members are extracted.
        overwrite: Always re-extract and replace existing output files.

    Returns:
        List of extracted or reused output paths.
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
            )

        if archive_type == "zip":
            with zipfile.ZipFile(src_file, "r") as archive:
                return _extract_zip(
                    archive,
                    outdir,
                    members,
                    overwrite,
                )

        with tarfile.open(src_file, "r:*") as archive:
            return _extract_tar(
                archive,
                outdir,
                members,
                overwrite,
            )


def p_f_unzip(
    src_file: str | Path,
    fns: Optional[List[str]] = None,
    outdir: str | Path = "./",
    overwrite: bool = False,
) -> List[Path]:
    """Compatibility wrapper for extracting ZIP files."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        members=fns,
        overwrite=overwrite,
    )


def p_f_untar(
    src_file: str | Path,
    fns: Optional[List[str]] = None,
    outdir: str | Path = "./",
    overwrite: bool = False,
) -> List[Path]:
    """Extract selected TAR archive members."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        members=fns,
        overwrite=overwrite,
    )


def p_f_gunzip(
    src_file: str | Path,
    outdir: str | Path = "./",
    overwrite: bool = False,
) -> List[Path]:
    """Decompress one GZIP file."""
    return p_f_extract(
        src_file,
        outdir=outdir,
        overwrite=overwrite,
    )


def p_unzip(src_fn: str, ext: list, outdir: str = ".", verbose: bool = False) -> list:
    """Unzip specific extensions from a zip file, optionally flattening directory structures.

    Args:
        src_fn: Path to the source zip file.
        ext: List of extensions to extract (e.g., ['shp', 'shx', 'dbf']).
        outdir: Directory to extract files into.
        verbose: Print debug info.

    Returns:
        List of paths to the extracted files.
    """
    if not Path(outdir).exists():
        Path(outdir).mkdir(parents=True, exist_ok=True)

    extracted_files = []

    try:
        with zipfile.ZipFile(src_fn, "r") as z:
            want_exts = [
                e.lower() if e.startswith(".") else f".{e.lower()}" for e in ext
            ]

            for file_info in z.infolist():
                if file_info.is_dir():
                    continue

                file_path = Path(file_info.filename)
                f_ext = file_path.suffix
                if f_ext.lower() in want_exts:
                    filename = file_path.name
                    target_path = Path(outdir) / filename

                    if verbose:
                        logger.info(f"Extracting {filename}...")

                    with z.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                    extracted_files.append(str(target_path))

    except zipfile.BadZipFile:
        logger.error(f"Bad Zip File: {src_fn}")
    except Exception as e:
        logger.error(f"Unzip error {src_fn}: {e}")

    return extracted_files
