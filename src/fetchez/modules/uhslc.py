#!/usr/bin/env python

"""
fetchez.modules.uhslc
~~~~~~~~~~~~~~~~~~~~~

Fetch global high-frequency tide gauge data from the University
of Hawaii Sea Level Center (UHSLC).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import logging
from pathlib import Path

from fetchez import cli, core
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

# UHSLC Endpoints
UHSLC_META_URL = "https://uhslc.soest.hawaii.edu/data/meta.geojson"
UHSLC_DATA_BASE = "https://uhslc.soest.hawaii.edu"


@cli.cli_opts(
    help_text="University of Hawaii Sea Level Center (UHSLC)",
    quality='Data quality: "rq" (Research Quality) or "fd" (Fast Delivery)',
    resolution='Time resolution: "hourly" or "daily"',
)
class UHSLC(FetchModule):
    name = "uhslc"
    meta_category = "Oceanography"
    meta_desc = "UHSLC Global Tide Gauge Data"
    meta_agency = "UHSLC"
    meta_tags = ["tides", "water level", "uhslc", "hourly", "global"]
    meta_region = "Global"
    meta_resolution = "Station"
    meta_license = "Public Domain / Open"
    meta_urls = {"home": "https://uhslc.soest.hawaii.edu/"}

    """
    Fetch high-frequency water level data from UHSLC.

    Filters the global UHSLC GeoJSON metadata list by the requested
    bounding box, then constructs direct URLs to the Fast Delivery (FD)
    or Research Quality (RQ) CSV datasets.
    """

    def __init__(
        self,
        quality: str | None = "rq",
        resolution: str | None = "hourly",
        name: str | None = "uhslc",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.quality = quality.lower() if quality else "rq"
        self.resolution = resolution.lower() if resolution else "hourly"

        if self.quality not in ["rq", "fd"]:
            self.quality = "rq"
        if self.resolution not in ["hourly", "daily"]:
            self.resolution = "hourly"

        self.quality_dict = {"rq": "woce", "fd": "fast"}

    def run(self):
        """Execute the UHSLC fetch logic."""

        if self.wgs_region is None:
            logger.error("A region bounding box is required to fetch UHSLC stations.")
            return self

        logger.debug(f"Fetching UHSLC master metadata from {UHSLC_META_URL}...")

        if not Path(self._outdir).exists():
            Path(self._outdir).mkdir(parents=True, exist_ok=True)

        local_meta = Path(Path(self._outdir) / "uhslc_meta.geojson")

        # Download the master station index
        if core.Fetch(UHSLC_META_URL).fetch_file(str(local_meta), verbose=False) != 0:
            logger.error("Failed to download the UHSLC metadata list.")
            return self

        w, e, s, n = self.wgs_region
        found_count = 0

        try:
            with open(local_meta, "r", encoding="utf-8") as f:
                data = json.load(f)

            features = data.get("features", [])

            for feature in features:
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})

                if not geom or not props:
                    continue

                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue

                lon, lat = coords[0], coords[1]
                uhslc_id = props.get("uhslc_id")
                station_name = props.get("location_name", "Unknown").strip()
                country = props.get("country", "Unknown").strip()

                if uhslc_id is None:
                    continue

                if (w <= lon <= e) and (s <= lat <= n):
                    # UHSLC uses 3-digit padded strings for IDs
                    formatted_id = f"{int(uhslc_id):03}"

                    prefix = "h" if self.resolution == "hourly" else "d"
                    if self.quality == "fd":
                        base = "/data/csv"
                        res = f"/{self.resolution}/"
                        ext = ".csv"
                    else:
                        base = ""
                        res = "/"
                        ext = ".dat"

                    data_url = f"{UHSLC_DATA_BASE}{base}/{self.quality_dict[self.quality]}{res}{prefix}{formatted_id}{ext}"

                    dst_name = (
                        f"uhslc_{formatted_id}_{self.quality}_{self.resolution}.csv"
                    )

                    self.add_entry_to_results(
                        url=data_url,
                        dst_fn=dst_name,
                        data_type="water_level",
                        agency="UHSLC",
                        title=f"Station {uhslc_id}: {station_name}, {country}",
                        geom={"type": "Point", "coordinates": [lon, lat]},
                    )
                    found_count += 1

        except Exception as e:
            logger.error(f"Error parsing UHSLC metadata: {e}")
        finally:
            if local_meta.exists():
                local_meta.unlink(mising_ok=True)

        logger.info(
            f"Found {found_count} UHSLC stations in the requested bounding box."
        )

        return self
