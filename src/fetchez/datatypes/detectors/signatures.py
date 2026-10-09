#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.datatypes.detectors.signatures
~~~~~~~~~~~

:copyright: (c) 2025 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from fetchez.datatypes.detectors.base import BaseDetector, Detection


class SignatureDetector(BaseDetector):
    name = "signature"

    meta_priority = 100

    SIGNATURES = {
        "49492a00": "raster",
        "49492b00": "raster",
        "4d4d002a": "raster",
        "504b0304": "archive",
        "504b0102": "archive",
    }

    def detect(self, entry):
        path = entry.get("dst_fn")

        if not path:
            return None

        magic_hex = self._read_magic_hex(path)
        data_type = self.SIGNATURES.get(magic_hex)

        if data_type is not None:
            return Detection(
                data_type=data_type,
                confidence=0.85,
                detector=self.name,
                reason=f"File Signature {magic_hex}",
            )
        else:
            return None

    @classmethod
    def _read_magic_hex(cls, file_path):
        return cls._read_magic_bytes(file_path).hex()

    @staticmethod
    def _read_magic_bytes(file_path):
        with open(file_path, "rb") as f:
            signature = f.read(4)
            return signature
        return b""
