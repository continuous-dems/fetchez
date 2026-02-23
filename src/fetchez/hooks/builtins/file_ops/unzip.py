#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.hooks.builtins.file_ops.unzip
~~~~~~~~~~~~~

Extract/Decompress files (.zip, .tar, .tar.gz, .tgz, .gz).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import zipfile
import tarfile
import gzip
import shutil
import logging

from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)


class Unzip(FetchHook):
    """Automatically extract/decompress files after download."""

    # Registry Metadata
    name = "unzip"
    desc = "Extract .zip, .tar, .tar.gz, and .gz files."
    stage = "file"
    category = "file-op"

    def __init__(self, remove=False, overwrite=False, **kwargs):
        """
        Args:
            remove (bool): Delete the original compressed file after extraction.
            overwrite (bool): Overwrite existing files.
        """
        super().__init__(**kwargs)
        self.remove = remove
        self.overwrite = overwrite

    def run(self, entries):
        out_entries = []
        for mod, entry in entries:
            file_path = entry.get("dst_fn")
            status = entry.get("status")

            if status != 0 or not file_path:
                out_entries.append((mod, entry))
                continue

            lower_path = file_path.lower()

            # --- HANDLE .ZIP ARCHIVES ---
            if lower_path.endswith(".zip"):
                extract_dir = os.path.dirname(file_path)
                try:
                    with zipfile.ZipFile(file_path, "r") as z:
                        files_to_extract = [
                            n for n in z.namelist() if not n.endswith("/")
                        ]

                        if not self.overwrite:
                            if all(
                                os.path.exists(os.path.join(extract_dir, f))
                                for f in files_to_extract
                            ):
                                logger.debug(
                                    f"Skipping unzip (files exist): {os.path.basename(file_path)}"
                                )
                                out_entries.extend(
                                    [
                                        (
                                            mod,
                                            {
                                                **entry,
                                                "dst_fn": os.path.join(extract_dir, f),
                                                "status": 0,
                                            },
                                        )
                                        for f in files_to_extract
                                    ]
                                )
                                continue

                        z.extractall(extract_dir)

                        for fname in files_to_extract:
                            full_path = os.path.join(extract_dir, fname)
                            out_entries.append(
                                (
                                    mod,
                                    {
                                        **entry,
                                        "dst_fn": full_path,
                                        "status": 0,
                                        "src_fn": file_path,
                                    },
                                )
                            )

                    if self.remove:
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Unzip failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- HANDLE .TAR / .TAR.GZ / .TGZ ARCHIVES ---
            elif lower_path.endswith((".tar", ".tar.gz", ".tgz")):
                extract_dir = os.path.dirname(file_path)
                try:
                    # 'r:*' automatically detects compression (gzip, bzip2, etc.)
                    with tarfile.open(file_path, "r:*") as tar:
                        # Extract only files (skip directory entries)
                        files_to_extract = [
                            m.name for m in tar.getmembers() if m.isfile()
                        ]

                        if not self.overwrite:
                            if all(
                                os.path.exists(os.path.join(extract_dir, f))
                                for f in files_to_extract
                            ):
                                logger.debug(
                                    f"Skipping untar (files exist): {os.path.basename(file_path)}"
                                )
                                out_entries.extend(
                                    [
                                        (
                                            mod,
                                            {
                                                **entry,
                                                "dst_fn": os.path.join(extract_dir, f),
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
                            full_path = os.path.join(extract_dir, fname)
                            out_entries.append(
                                (
                                    mod,
                                    {
                                        **entry,
                                        "dst_fn": full_path,
                                        "status": 0,
                                        "src_fn": file_path,
                                    },
                                )
                            )

                    if self.remove:
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Untar failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- HANDLE .GZ DECOMPRESSION (Single File) ---
            elif lower_path.endswith(".gz"):
                extracted_path = file_path[:-3]

                if not self.overwrite and os.path.exists(extracted_path):
                    logger.debug(
                        f"Skipping gunzip (file exists): {os.path.basename(file_path)}"
                    )
                    out_entries.append(
                        (mod, {**entry, "dst_fn": extracted_path, "status": 0})
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
                                "dst_fn": extracted_path,
                                "status": 0,
                                "src_fn": file_path,
                            },
                        )
                    )

                    if self.remove:
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass

                except Exception as e:
                    logger.error(f"Gunzip failed for {file_path}: {e}")
                    out_entries.append((mod, entry))

            # --- UNRECOGNIZED FORMAT ---
            else:
                out_entries.append((mod, entry))

        return out_entries
