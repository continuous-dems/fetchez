#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_of2005_1170
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Open-File Report 2005-1170 (Nearshore Benthic Habitat GIS for the Channel
Islands National Marine Sanctuary and Southern California State Fisheries Reserves).
"""

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from shapely.geometry import box, mapping
from tqdm.auto import tqdm

from fetchez import core
from fetchez import fred
from fetchez.modules.base import FetchModule
from fetchez.utils import str_or

logger = logging.getLogger(__name__)

OF1170_BASE_URL = "https://pubs.usgs.gov/of/2005/1170/"
OF1170_CATALOG_URL = f"{OF1170_BASE_URL}catalog.html"


class USGS_OF2005_1170(FetchModule):
    """Fetchez module to retrieve bathymetry contours, basemaps, dive observations,
    sidescan sonar, and benthic habitat shapefiles from USGS OFR 2005-1170.
    """

    # --- Registry Metadata ---
    name = "usgs_of2005_1170"
    meta_category = "Bathymetry"
    meta_desc = (
        "Channel Islands Nearshore Benthic Habitat GIS & 10m Bathymetric Contours"
    )
    meta_agency = "USGS"
    meta_resolution = "10 m (contours) / 1 m (sidescan)"
    meta_license = "Public Domain"
    meta_tags = [
        "california",
        "channel_islands",
        "bathymetry",
        "contours",
        "benthic",
        "usgs",
        "habitat",
    ]
    meta_urls = {
        "catalog": OF1170_CATALOG_URL,
    }

    # Known datasets mapped from the publication catalog
    CATALOG = {
        # Basemaps
        "cntr10m": {
            "path": "basemaps/cntr10m.tgz",
            "type": "vector",
            "desc": "10 Meter Bathymetric Contours",
        },
        "calif3nm": {
            "path": "basemaps/calif3nm.tgz",
            "type": "vector",
            "desc": "California state waters (3 nautical miles)",
        },
        "channel_islands_mpa": {
            "path": "basemaps/Channel_Islands_MPA.tgz",
            "type": "vector",
            "desc": "Existing MPA boundaries",
        },
        "scampa": {
            "path": "basemaps/scampa.tgz",
            "type": "vector",
            "desc": "Proposed MPA boundaries",
        },
        "scasmpl": {
            "path": "usseabed/scasmpl.tgz",
            "type": "vector",
            "desc": "Location and contents of samples (usSEABED)",
        },
        "scasstrk": {
            "path": "basemaps/scasstrk.tgz",
            "type": "vector",
            "desc": "Survey track lines",
        },
        # Observations
        "scav2obs": {
            "path": "observations/scav2obs.tgz",
            "type": "vector",
            "desc": "Visual observations from dives",
        },
        # Sidescan Sonar Images (1m pixel rasters)
        "nanp1m": {
            "path": "sidescan/nanp1m.tgz",
            "type": "raster",
            "desc": "North Anacapa Passage Sidescan (1m)",
        },
        "sana1m": {
            "path": "sidescan/sana1m.tgz",
            "type": "raster",
            "desc": "South Anacapa Island Sidescan (1m)",
        },
        "sanp1m": {
            "path": "sidescan/sanp1m.tgz",
            "type": "raster",
            "desc": "South Anacapa Passage Sidescan (1m)",
        },
        "secru1m": {
            "path": "sidescan/secru1m.tgz",
            "type": "raster",
            "desc": "Southeast Santa Cruz Island Sidescan (1m)",
        },
        # Benthic Habitat Polygons
        "nanphab": {
            "path": "habitat/nanphab.tgz",
            "type": "vector",
            "desc": "North Anacapa Passage Habitat Polygons",
        },
        "sanahab": {
            "path": "habitat/sanahab.tgz",
            "type": "vector",
            "desc": "South Anacapa Island Habitat Polygons",
        },
        "sanphab": {
            "path": "habitat/sanphab.tgz",
            "type": "vector",
            "desc": "South Anacapa Passage Habitat Polygons",
        },
        "secrhab": {
            "path": "habitat/secrhab.tgz",
            "type": "vector",
            "desc": "Southeast Santa Cruz Island Habitat Polygons",
        },
    }

    def __init__(self, datatype: str = "cntr10m", update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.datatype = str_or(datatype.lower(), "cntr10m")
        self.force_update = update

        # Initialize the local feature registry
        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    def _parse_bbox_from_metadata(self, url: str):
        """Fetch the FGDC text metadata and extract bounding coordinates using regex."""
        # Use Fetchez's core fetcher to download the text content
        try:
            response = core.Fetch(url).fetch_html()
            if response is None:
                return None

            # If response is an lxml parsed tree (from fetch_html), convert it back to text
            try:
                text_content = response.text_content()
            except AttributeError:
                text_content = str(response)

            # Regex to find FGDC Bounding Coordinates
            try:
                _w = re.search(r"West_Bounding_Coordinate:\s*([-\d\.]+)", text_content)
                _e = re.search(r"East_Bounding_Coordinate:\s*([-\d\.]+)", text_content)

                _n = re.search(r"North_Bounding_Coordinate:\s*([-\d\.]+)", text_content)
                _s = re.search(r"South_Bounding_Coordinate:\s*([-\d\.]+)", text_content)

                if _w is None or _e is None or _n is None or _s is None:
                    raise ValueError("Could not parse bounds from FGDC")
                else:
                    w = _w.group(1)
                    e = _e.group(1)
                    n = _n.group(1)
                    s = _s.group(1)

                # Create a GeoJSON polygon dict using Shapely
                return mapping(box(w, s, e, n))
            except (AttributeError, ValueError) as exc:
                logger.debug(
                    "[%s] Failed to parse bounding box from %s: %s", self.name, url, exc
                )
                return None
        except Exception:
            pass

    def update_fred(self):
        """Scrape metadata for all known targets and build the FRED spatial index."""
        logger.info("Building FRED index for USGS OFR 2005-1170 metadata...")

        count = 0
        with tqdm(
            total=len(self.CATALOG), desc="Parsing Metadata", disable=self.silent
        ) as pbar:
            for key, info in self.CATALOG.items():
                pbar.update()

                dataset_tgz = urljoin(OF1170_BASE_URL, info["path"])
                # USGS convention for these OFRs: .tgz base name + .txt
                metadata_url = dataset_tgz.replace(".tgz", ".txt")

                geom = self._parse_bbox_from_metadata(metadata_url)

                # Fallback to entire region if metadata doesn't parse cleanly,
                # ensuring the data is at least reachable without -R bounds
                if geom is None:
                    geom = mapping(box(-121.0, 33.0, -118.0, 35.0))

                self.FRED.add_survey(
                    geom=geom,
                    Name=key,
                    ID=key,
                    Agency="USGS",
                    DataLink=dataset_tgz,
                    MetadataLink=metadata_url,
                    DataType=info["type"],
                    DataSource=self.name,
                    Info=info["desc"],
                )
                count += 1

        if count > 0:
            logger.info("Added %d new datasets to FRED.", count)
            self.FRED.save()

    def run(self):
        """Populate results by querying the FRED index against the requested region."""

        # Search the local FRED geojson for intersecting datasets
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info(
                "[%s] No datasets found intersecting the requested region.", self.name
            )
            return self

        # Filter against the requested datatype categories
        for surv in results:
            dataset_id = surv.get("ID")

            # Skip if user specified a specific dataset and this isn't it,
            # or if they specified a folder category and it doesn't belong to it
            if self.datatype != "all":
                if self.datatype in self.CATALOG and dataset_id != self.datatype:
                    continue
                # Folder category match (e.g. "sidescan" or "habitat")
                elif self.datatype not in self.CATALOG and not self.CATALOG[dataset_id][
                    "path"
                ].startswith(f"{self.datatype}/"):
                    continue

            data_link = surv.get("DataLink")
            if data_link:
                self.add_entry_to_results(
                    url=data_link,
                    dst_fn=Path(data_link).name,
                    data_type=surv.get("DataType", "vector"),
                    title=f"USGS OFR 2005-1170: {surv.get('Info')}",
                    vdatum="MSL",
                    hdatum="NAD83 / UTM Zone 10N",
                    info=surv.get("Info"),
                )

        return self
