#!/usr/bin/env python

"""
fetchez.modules.psmsl
~~~~~~~~~~~~~~~~~~~~~

Fetch global Mean Sea Level data from the Permanent Service for Mean Sea Level (PSMSL).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import csv
import logging
from pathlib import Path

from fetchez import cli, core
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

# PSMSL Endpoints
PSMSL_BASE = "https://psmsl.org/data/obtaining"
STATION_LIST_URL = f"{PSMSL_BASE}/rlr.monthly.data/filelist.txt"


@cli.cli_opts(
    help_text="Permanent Service for Mean Sea Level (PSMSL)",
    datatype='Data format: "rlr" (Revised Local Reference) or "metric"',
)
class PSMSL(FetchModule):
    name = "psmsl"
    meta_category = "Oceanography"
    meta_desc = "Permanent Service for Mean Sea Level (PSMSL) Tide Gauges"
    meta_agency = "PSMSL"
    meta_tags = ["tides", "msl", "sea level", "psmsl", "global"]
    meta_region = "Global"
    meta_resolution = "Station"
    meta_license = "Public Domain / Open"
    meta_urls = {"home": "https://psmsl.org/"}

    """Fetch global tide gauge and MSL data from PSMSL.

    The module reads the PSMSL master filelist to find stations that
    intersect the requested bounding box, then builds the URLs to fetch
    either the RLR or Metric time-series datasets.
    """

    def __init__(
        self,
        datatype: str | None = "rlr",
        name: str | None = "psmsl",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.datatype = datatype.lower() if datatype else "rlr"

    def run(self):
        """Execute the PSMSL fetch logic."""

        if self.wgs_region is None:
            logger.error("A region bounding box is required to fetch PSMSL stations.")
            return self

        logger.debug(f"Fetching PSMSL station master list from {STATION_LIST_URL}...")

        Path(self._outdir).mkdir(parents=True, exist_ok=True)
        local_list = Path(self._outdir) / "psmsl_filelist.txt"

        # Download the index
        if core.Fetch(STATION_LIST_URL).fetch_file(local_list, verbose=False) != 0:
            logger.error("Failed to download the PSMSL station list.")
            return self

        w, e, s, n = self.wgs_region
        found_count = 0

        try:
            with open(local_list, "r", encoding="utf-8") as f:
                # The filelist is semi-colon delimited
                reader = csv.reader(f, delimiter=";")
                for row in reader:
                    if len(row) < 4:
                        continue

                    try:
                        station_id = row[0].strip()
                        lat = float(row[1].strip())
                        lon = float(row[2].strip())
                        station_name = row[3].strip()
                    except ValueError:
                        continue

                    if (w <= lon <= e) and (s <= lat <= n):
                        if self.datatype == "metric":
                            data_url = (
                                f"{PSMSL_BASE}/met.monthly.data/{station_id}.metdata"
                            )
                        else:
                            data_url = (
                                f"{PSMSL_BASE}/rlr.monthly.data/{station_id}.rlrdata"
                            )

                        dst_name = f"psmsl_{station_id}_{self.datatype}.csv"

                        self.add_entry_to_results(
                            url=str(data_url),
                            dst_fn=str(dst_name),
                            data_type=self.datatype,
                            agency="PSMSL",
                            title=f"Station {station_id}: {station_name}",
                            geom={"type": "Point", "coordinates": [lon, lat]},
                        )
                        found_count += 1

        except Exception as e:
            logger.error(f"Error parsing PSMSL list: {e}")
        finally:
            local_list.unlink(missing_ok=True)

        logger.info(
            f"Found {found_count} PSMSL stations in the requested bounding box."
        )

        return self
