#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.vdatum
~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA Tidal Grids (MLLW, MHHW) from vdatum.noaa.gov.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from typing import Optional
from fetchez import core
from fetchez import cli
from fetchez import fred

logger = logging.getLogger(__name__)

VDATUM_DATA_URL = "https://vdatum.noaa.gov/download/data/"
VDATUM_REGIONS = [
    "TIDAL",
    "IGLD85",
    "XGEOID16B",
    "XGEOID17B",
    "XGEOID18B",
    "XGEOID19B",
    "XGEOID20B",
    "VERTCON",
]


@cli.cli_opts(
    help_text="NOAA VDatum Tidal Grids",
    datatype='Filter by datum type (e.g., "mllw", "mhhw", "tidal").',
    update="Force a re-scrape of the NOAA website.",
)
class VDatum(core.FetchModule):
    """Fetch NOAA VDatum grids, specifically Tidal Datums (MLLW, MHHW).

    Because these grids are not available in the PROJ CDN, this module
    performs a "heavy" discovery process:

    - Downloads regional ZIP files from NOAA.
    - Inspects internal .inf files to determine bounding boxes.
    - Builds a local spatial index (FRED) for future fast lookups.
    """

    def __init__(self, datatype: Optional[str] = None, update: bool = False, **kwargs):
        super().__init__(name="vdatum", **kwargs)
        self.datatype = datatype.lower() if datatype else None
        self.force_update = update

        self.fred = fred.FRED("vdatum", local=False)

    def _scrape_and_index(self):
        """Download zips, parse .inf, update index."""

        logger.info("Initializing VDatum Index (This may take a moment)...")

        temp_dir = os.path.join(self._outdir, "temp_idx")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        for region in VDATUM_REGIONS:
            fname = f"{region}.zip"
            if region == "TIDAL":
                fname = "DEVAemb12_8301.zip"  # Example mapping, may vary
            elif "XGEOID" in region:
                fname = f"vdatum_{region}.zip"

            url = f"{VDATUM_DATA_URL}{fname}"
            local_zip = os.path.join(temp_dir, fname)

            logger.info(f"Indexing {region}...")
            if core.Fetch(url).fetch_file(local_zip) != 0:
                continue

            try:
                import zipfile

                with zipfile.ZipFile(local_zip, "r") as z:
                    for zf in z.namelist():
                        if zf.endswith(".inf"):
                            with z.open(zf) as inf:
                                content = inf.read().decode("utf-8", errors="ignore")
                                meta = self._parse_inf(content)

                                if meta:
                                    geom = {
                                        "type": "Polygon",
                                        "coordinates": [
                                            [
                                                [meta["w"], meta["s"]],
                                                [meta["e"], meta["s"]],
                                                [meta["e"], meta["n"]],
                                                [meta["w"], meta["n"]],
                                                [meta["w"], meta["s"]],
                                            ]
                                        ],
                                    }

                                    self.fred.add_survey(
                                        geom,
                                        Name=zf,
                                        ID=region,
                                        Agency="NOAA",
                                        DataLink=url,
                                        DataType="tidal"
                                        if region == "TIDAL"
                                        else "geoid",
                                        DataSource="vdatum",
                                    )
            except Exception as e:
                logger.warning(f"Failed to parse {fname}: {e}")

            if os.path.exists(local_zip):
                os.remove(local_zip)

        self.fred.save()
        logger.info("VDatum Indexing Complete.")

    def _parse_inf(self, text):
        """Helper to extract bounds from VDatum INF format."""

        d = {}
        for line in text.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip().lower().split(".")[-1]] = v.strip()

        try:
            return {
                "w": float(d.get("minlon", 0)),
                "e": float(d.get("maxlon", 0)),
                "s": float(d.get("minlat", 0)),
                "n": float(d.get("maxlat", 0)),
            }
        except Excetion as e:
            return None

    def run(self):
        if self.force_update or not self.fred.features:
            self._scrape_and_index()

        if not self.fred.features:
            logger.error("VDatum index is empty. Scrape failed.")
            return self

        results = self.fred.search(region=self.region)

        for r in results:
            if self.datatype and self.datatype not in r.get("DataType", ""):
                continue

            self.add_entry_to_results(
                url=r["DataLink"],
                dst_fn=os.path.basename(r["DataLink"]),
                data_type=r["DataType"],
                agency="NOAA",
                title=f"VDatum Grid ({r['ID']})",
            )

        return self
