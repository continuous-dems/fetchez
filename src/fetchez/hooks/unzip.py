#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.unzip
~~~~~~~~~~~~~

Extract/Decompress files (.zip, .tar, .tar.gz, .tgz, .gz).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import zipfile
import tarfile
import gzip
import shutil
import logging
from pathlib import Path

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Unzip(FetchHook):
    """Automatically extract/decompress files after download."""

    name = "unzip"
    meta_desc = "Extract .zip, .tar, .tar.gz, and .gz files."
    meta_stage = "file"
    meta_category = "file-op"

    def __init__(self, remove=False, overwrite=False, **kwargs):
        """Decompress and/or extract data from archives.

        Args:
            remove: Delete the original compressed file after extraction.
            overwrite: Overwrite existing files.
        """

        super().__init__(**kwargs)
        self.remove = remove
        self.overwrite = overwrite

    def run(self, entries):
        out_entries = []
        for mod, entry in entries:
            file_path = Path(entry.get("dst_fn"))
            status = entry.get("status")

            if (status is not None and status != 0) or not file_path:
                out_entries.append((mod, entry))
                continue

            # --- .ZIP ARCHIVES ---
            if file_path.suffix.lower() == ".zip":
                extract_dir = file_path.parent
                try:
                    with zipfile.ZipFile(file_path, "r") as z:
                        files_to_extract = [
                            n for n in z.namelist() if not n.endswith("/")
                        ]

                        if not self.overwrite:
                            if all(
                                Path(extract_dir / f).exists() for f in files_to_extract
                            ):
                                logger.debug(
                                    f"Skipping unzip (files exist): {file_path.name}"
                                )
                                out_entries.extend(
                                    [
                                        (
                                            mod,
                                            {
                                                **entry,
                                                "dst_fn": str(Path(extract_dir / f)),
                                                "status": 0,
                                            },
                                        )
                                        for f in files_to_extract
                                    ]
                                )
                                continue

                        z.extractall(extract_dir)
                        for fname in files_to_extract:
                            full_path = Path(extract_dir / fname)
                            out_entries.append(
                                (
                                    mod,
                                    {
                                        **entry,
                                        "dst_fn": str(full_path),
                                        "status": 0,
                                        "src_fn": str(file_path),
                                    },
                                )
                            )

                    if self.remove:
                        try:
                            Path(file_path).unlink()
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Unzip failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- .TAR / .TAR.GZ / .TGZ ARCHIVES ---
            elif file_path.name.lower().endswith((".tar", ".tar.gz", ".tgz")):
                extract_dir = file_path.parent
                try:
                    # 'r:*' automatically detects compression (gzip, bzip2, etc.)
                    with tarfile.open(file_path, "r:*") as tar:
                        files_to_extract = [
                            m.name for m in tar.getmembers() if m.isfile()
                        ]

                        if not self.overwrite:
                            if all(
                                Path(extract_dir / f).exists() for f in files_to_extract
                            ):
                                logger.debug(
                                    f"Skipping untar (files exist): {file_path.name}"
                                )
                                out_entries.extend(
                                    [
                                        (
                                            mod,
                                            {
                                                **entry,
                                                "dst_fn": str(Path(extract_dir / f)),
                                                "status": 0,
                                            },
                                        )
                                        for f in files_to_extract
                                    ]
                                )
                                continue

                        if hasattr(tarfile, "data_filter"):
                            tar.extractall(path=extract_dir, filter="data")
                        else:
                            tar.extractall(path=extract_dir)

                        for fname in files_to_extract:
                            full_path = Path(extract_dir / fname)
                            out_entries.append(
                                (
                                    mod,
                                    {
                                        **entry,
                                        "dst_fn": str(full_path),
                                        "status": 0,
                                        "src_fn": str(file_path),
                                    },
                                )
                            )

                    if self.remove:
                        try:
                            file_path.unlink()
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Untar failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- .GZ DECOMPRESSION (Single File) ---
            elif file_path.suffix.lower() == ".gz":
                extracted_path = file_path.with_suffix("")
                if not self.overwrite and extracted_path.exists():
                    logger.debug(
                        f"Skipping gunzip (file exists): {extracted_path.name}"
                    )
                    out_entries.append(
                        (mod, {**entry, "dst_fn": str(extracted_path), "status": 0})
                    )
                    continue

                try:
                    with gzip.open(file_path, "rb") as f_in:
                        with open(extracted_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    out_entries.append(
                        (
                            mod,
                            {
                                **entry,
                                "dst_fn": str(extracted_path),
                                "status": 0,
                                "src_fn": str(file_path),
                            },
                        )
                    )

                    if self.remove:
                        try:
                            file_path.unlink()
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Gunzip failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- UNRECOGNIZED FORMAT ---
            else:
                out_entries.append((mod, entry))

        return out_entries
