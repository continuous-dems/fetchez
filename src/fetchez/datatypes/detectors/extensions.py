#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.datatypes.detectors.extensions
~~~~~~~~~~~

:copyright: (c) 2025 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path
from urllib.parse import urlsplit

from fetchez.datatypes.detectors.base import BaseDetector, Detection


class ExtensionDetector(BaseDetector):
    name = "extension"

    meta_priority = 100

    EXTENSIONS = {
        ".csv": "table",
        ".tif": "raster",
        ".tiff": "raster",
        ".vrt": "raster",
        ".shp": "vector",
        ".geojson": "vector",
        ".las": "point-cloud",
        ".laz": "point-cloud",
        ".zip": "archive",
        ".tar": "archive",
        ".tgz": "archive",
    }

    def detect(self, entry):
        path = entry.get("dst_fn") or entry.get("url")

        if not path:
            return None

        suffix = self._suffix_from_locator(path)
        data_type = self.EXTENSIONS.get(suffix)

        if not data_type:
            return None

        return Detection(
            data_type=data_type,
            confidence=0.5,
            detector=self.name,
            reason=f"Filename extension {suffix}",
        )

    @staticmethod
    def _suffix_from_locator(locator):
        locator = str(locator)

        if "://" in locator:
            locator = urlsplit(locator).path

        return Path(locator).suffix.lower()
