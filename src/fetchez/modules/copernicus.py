#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.copernicus
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch data from the Copernicus Digital Elevation Model (DEM).

:copyright: (c) 2022 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from typing import Optional, List, Any
from tqdm import tqdm

from fetchez import core
from fetchez import fred
from fetchez import cli

logger = logging.getLogger(__name__)

COP30_BUCKET_URL = "https://opentopography.s3.sdsc.edu/minio/raster/COP30/COP30_hh/"
COP30_DOWNLOAD_URL = (
    "https://opentopography.s3.sdsc.edu/minio/download/raster/COP30/COP30_hh/"
)
COP30_VRT_URL = (
    "https://opentopography.s3.sdsc.edu/minio/download/raster/COP30/COP30_hh.vrt?token="
)

COP10_URL = "https://gisco-services.ec.europa.eu/dem/copernicus/outD/"
COP10_AUX_URL = "https://gisco-services.ec.europa.eu/dem/copernicus/outA/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "referer": COP30_BUCKET_URL,
}


# =============================================================================
# Copernicus Module
# =============================================================================
@cli.cli_opts(
    help_text="COPERNICUS satellite elevation data (COP-30 / COP-10)",
    datatype="Set data type: '1'=COP-30 (Global), '3'=COP-10 (Europe)",
    update="Force update of the local index (FRED)",
)
class CopernicusDEM(core.FetchModule):
    """The Copernicus DEM is a Digital Surface Model (DSM) which
    represents the surface of the Earth including buildings,
    infrastructure and vegetation.

    Datatypes:
      '1' = COP-30 (Global ~30m)
      '3' = COP-10 (Europe ~10m)

    The module relies on a local index (FRED) which it will attempt to
    auto-update on first run.
    """

    def __init__(self, datatype: Optional[str] = None, update: bool = False, **kwargs):
        super().__init__(name="copernicus", **kwargs)
        self.datatype = datatype
        self.force_update = update
        self.where: List[Any] = []

        self.headers = HEADERS

        # Initialize FRED (Local Index)
        self.FRED = fred.FRED(name=self.name)

        # Check if we need to update the index
        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    def _create_geojson_box(self, xmin, xmax, ymin, ymax):
        """Helper to create a GeoJSON Polygon dict."""

        return {
            "type": "Polygon",
            "coordinates": [
                [[xmin, ymin], [xmin, ymax], [xmax, ymax], [xmax, ymin], [xmin, ymin]]
            ],
        }

    def _update_cop10(self):
        """Scrape and parse COP-10 (European 10m) datasets."""

        logger.info("Scanning COP-10 (European) datasets...")
        page = core.Fetch(COP10_URL).fetch_html()
        if page is None:
            return

        rows = page.xpath('//a[contains(@href, ".zip")]/@href')

        # Build set of existing IDs to skip duplicates
        existing_ids = {
            f["properties"]["ID"]
            for f in self.FRED.features
            if f["properties"].get("ID")
        }
        count = 0

        with tqdm(total=len(rows), desc="Parsing COP-10", disable=self.silent) as pbar:
            for row in rows:
                pbar.update()
                sid = row.split(".")[0]

                if sid in existing_ids:
                    continue

                try:
                    # Parse filename (e.g., ..._x30y40.zip)
                    # Expected format typically ends with coordinates like _x30y40
                    spat = sid.split("_")[-1]
                    x_str = spat.split("x")[-1]
                    y_str = spat.split("x")[0].split("y")[-1]
                    x = int(x_str)
                    y = int(y_str)

                    # COP-10 tiles are typically 10x10 degrees
                    geom = self._create_geojson_box(x, x + 10, y, y + 10)

                    self.FRED.add_survey(
                        geom=geom,
                        Name=sid,
                        ID=sid,
                        Agency="EU",
                        DataLink=f"{COP10_URL}{row}",
                        DataType="3",  # COP-10
                        DataSource="copernicus",
                        Info="COP-10",
                        Resolution="10m",
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse COP-10 file {row}: {e}")

        if count > 0:
            logger.info(f"Added {count} new COP-10 datasets.")

    def _update_cop30(self):
        """Parse COP-30 (Global 30m) datasets from VRT."""

        logger.info("Scanning COP-30 (Global) datasets...")
        f = core.Fetch(COP30_VRT_URL, headers=self.headers)
        page = f.fetch_xml()

        if page is None:
            return

        fns = page.findall(".//SourceFilename")

        existing_ids = {
            f["properties"]["ID"]
            for f in self.FRED.features
            if f["properties"].get("ID")
        }
        count = 0

        with tqdm(total=len(fns), desc="Parsing COP-30", disable=self.silent) as pbar:
            for fn in fns:
                pbar.update()

                # Filename example: COP30_hh_10_N30_00_W120_00_DEM.tif
                raw_fn = fn.text
                sid = raw_fn.split("/")[-1].split(".")[0]

                if sid in existing_ids:
                    continue

                try:
                    # Parse Spatial Info
                    # Format: ..._10_Nxx_00_Wxxx_00_DEM
                    spat = raw_fn.split("_10_")[-1].split("_DEM")[0]

                    xsplit = "_E" if "E" in spat else "_W"
                    ysplit = "S" if "S" in spat else "N"

                    parts = spat.split(xsplit)
                    y_part = parts[0].split(ysplit)[-1].split("_")[0]
                    x_part = parts[-1].split("_")[0]

                    y = int(y_part)
                    x = int(x_part)

                    if xsplit == "_W":
                        x = x * -1
                    if ysplit == "S":
                        y = y * -1

                    # COP-30 tiles are 1x1 degree
                    geom = self._create_geojson_box(x, x + 1, y, y + 1)

                    self.FRED.add_survey(
                        geom=geom,
                        Name=sid,
                        ID=sid,
                        Agency="EU",
                        DataLink=f"{COP30_DOWNLOAD_URL}{raw_fn.split('/')[-1]}?token=",
                        DataType="1",  # COP-30
                        DataSource="copernicus",
                        Info="COP-30",
                        Resolution="30m",
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse COP-30 file {raw_fn}: {e}")

        if count > 0:
            logger.info(f"Added {count} new COP-30 datasets.")

    def update_fred(self):
        """Run the scrapers and save to FRED."""

        try:
            self._update_cop10()
            self._update_cop30()
            self.FRED.save()
            logger.info(
                f"FRED index updated. Total features: {len(self.FRED.features)}"
            )
        except Exception as e:
            logger.error(f"Error updating Copernicus FRED: {e}")

    def run(self):
        """Run the COPERNICUS DEM fetching module."""

        search_where = self.where.copy()
        if self.datatype is not None:
            search_where.append(f"DataType = '{self.datatype}'")

        # Search FRED
        results = self.FRED.search(
            region=self.region, where=search_where, layer="copernicus"
        )

        if not results:
            logger.info("No matching datasets found in FRED index.")
            return

        with tqdm(
            total=len(results),
            desc="Processing Copernicus Results",
            disable=self.silent,
            leave=False,
        ) as pbar:
            for surv in results:
                pbar.update()

                links = surv.get("DataLink", "").split(",")
                dtype = surv.get("DataType", "1")
                res = surv.get("Resolution", "30m")

                for link in links:
                    if not link:
                        continue

                    # Clean URL (remove query params for filename)
                    clean_name = link.split("/")[-1].split("?")[0]

                    # Enriched Metadata
                    self.add_entry_to_results(
                        url=link,
                        dst_fn=clean_name,
                        data_type=dtype,
                        resolution=res,
                        srs="epsg:4326+3855",
                        source="Copernicus",
                        info=surv.get("Info", ""),
                    )

        return self
