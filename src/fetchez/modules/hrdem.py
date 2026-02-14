#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.hrdem
~~~~~~~~~~~~~~~~~~~~~

Fetch High-Resolution Digital Elevation Model (HRDEM) data from Canada (NRCAN).

Supports two modes:
- Mosaic (Default): Fetches seamless tiles via the CanElevation STAC API.
- Fetches raw project files via FTP footprints (requires GDAL/OGR).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import requests
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

# New STAC API for Mosaic
NRCAN_STAC_URL = "https://datacube.services.geo.ca/stac/api/search"

# Legacy FTP Footprints
HRDEM_FOOTPRINTS_URL = (
    "ftp://ftp.maps.canada.ca/pub/elevation/dem_mne/"
    "highresolution_hauteresolution/Datasets_Footprints.zip"
)


# =============================================================================
# HRDEM Module
# =============================================================================
@cli.cli_opts(
    help_text="Canada HRDEM (Mosaic & Legacy)",
    mode=" 'mosaic' (default) or 'legacy'",
    resolution=" '1m' (default) or '2m' (Mosaic only)",
    model=" 'dtm' (Terrain) or 'dsm' (Surface). Default: dtm",
)
class HRDEM(core.FetchModule):
    """
    Fetch High-Resolution Digital Elevation Model (HRDEM) data for Canada.

    Mode 1: Mosaic (Default)
      Queries the NRCAN STAC API to find seamless Cloud-Optimized GeoTIFFs (COGs).
      This is the preferred method for most users.

    Mode 2: Legacy
      Downloads the 'Datasets_Footprints.zip', extracts the shapefile,
      and finds raw project tiles. Requires GDAL/OGR.

    References:
      - https://nrcan.github.io/CanElevation/stac-dem-mosaics/
      - https://open.canada.ca/data/en/dataset/957782bf-847c-4644-a757-e383c0057995
    """

    def __init__(
        self, mode: str = "mosaic", resolution: str = "1m", model: str = "dtm", **kwargs
    ):
        super().__init__(name="hrdem", **kwargs)
        self.mode = mode.lower()
        self.resolution = resolution.lower()
        self.model = model.lower()

    def _run_mosaic(self):
        """Query the CanElevation STAC API."""

        if self.region is None:
            return

        w, e, s, n = self.region

        collection_id = f"hrdem-mosaic-{self.resolution}"

        logger.info(f"Querying NRCAN STAC for {collection_id} ({self.model})...")

        payload = {"collections": [collection_id], "bbox": [w, s, e, n], "limit": 100}

        try:
            r = requests.post(NRCAN_STAC_URL, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()

            features = data.get("features", [])
            logger.info(f"Found {len(features)} intersecting tiles.")

            for feat in features:
                assets = feat.get("assets", {})
                # props = feat.get("properties", {})
                tile_id = feat.get("id")

                asset = assets.get(self.model)
                if not asset:
                    continue

                url = asset.get("href")
                if not url:
                    continue

                self.add_entry_to_results(
                    url=url,
                    dst_fn=f"hrdem_{self.resolution}_{self.model}_{tile_id}.tif",
                    data_type="geotiff",
                    agency="NRCAN",
                    title=f"HRDEM Mosaic {tile_id}",
                )

        except Exception as e:
            logger.error(f"STAC Query failed: {e}")

    def _run_legacy(self):
        """Original footprint-based fetch (requires GDAL/OGR)."""

        try:
            from osgeo import ogr
        except ImportError:
            logger.error("Legacy mode requires GDAL/OGR. Install via: pip install gdal")
            return

        v_zip = os.path.join(self._outdir, "Datasets_Footprints.zip")
        logger.info("Downloading HRDEM footprints (Legacy)...")

        status = core.Fetch(HRDEM_FOOTPRINTS_URL).fetch_file(v_zip)
        if status != 0:
            logger.error("Failed to download footprints.")
            return

        try:
            # Simple unzip
            import zipfile

            with zipfile.ZipFile(v_zip, "r") as z:
                z.extractall(self._outdir)

            v_shp = None
            for root, dirs, files in os.walk(self._outdir):
                for f in files:
                    if f.endswith(".shp") and "Footprint" in f:
                        v_shp = os.path.join(root, f)
                        break

            if not v_shp:
                logger.error("Could not find shapefile in footprints zip.")
                return

            ds = ogr.Open(v_shp)
            if not ds:
                return

            layer = ds.GetLayer()

            w, e, s, n = self.region
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(w, s)
            ring.AddPoint(e, s)
            ring.AddPoint(e, n)
            ring.AddPoint(w, n)
            ring.AddPoint(w, s)
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)

            layer.SetSpatialFilter(poly)

            matches = 0
            for feature in layer:
                field_name = "Ftp_dtm" if self.model == "dtm" else "Ftp_dsm"
                link = feature.GetField(field_name)

                if link:
                    self.add_entry_to_results(
                        url=link,
                        dst_fn=link.split("/")[-1],
                        data_type="geotiff",
                        agency="NRCAN",
                        title="HRDEM Legacy Tile",
                    )
                    matches += 1

            logger.info(f"Found {matches} legacy tiles.")
            ds = None

        except Exception as e:
            logger.error(f"Legacy processing error: {e}")

        finally:
            # Cleanup zip
            if os.path.exists(v_zip):
                os.remove(v_zip)

    def run(self):
        if self.mode == "legacy":
            self._run_legacy()
        else:
            self._run_mosaic()
        return self
