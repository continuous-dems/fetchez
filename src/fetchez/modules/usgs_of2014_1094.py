#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_of2014_1094
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Open-File Report 2014-1094: California State Waters Map Series Data Catalog.
Contains high-resolution bathymetry, acoustic backscatter, and seismic-reflection data.
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

OFR2014_1094_BASE_URL = "https://pubs.usgs.gov/of/2014/1094/"
OFR2014_1094_CATALOG_URL = f"{OFR2014_1094_BASE_URL}datacatalog.html"


class USGS_OF2014_1094(FetchModule):
    """Fetchez module to retrieve bathymetry, backscatter, and seismic data from USGS OFR 2014-1094."""

    # --- Registry Metadata ---
    name = "usgs_of2014_1094"
    meta_category = "Bathymetry"
    meta_desc = "USGS OFR 2014-1094: California State Waters Map Series Data Catalog"
    meta_agency = "USGS"
    meta_resolution = "Varies"
    meta_license = "Public Domain"
    meta_tags = [
        "california",
        "bathymetry",
        "backscatter",
        "coastal",
        "usgs",
        "seismic",
    ]
    meta_urls = {
        "catalog": OFR2014_1094_CATALOG_URL,
    }

    def __init__(self, datatype: str = "all", update: bool = False, **kwargs):
        """Initialize the USGS OFR 2014-1094 fetch module.

        :param datatype: Filter by data keyword (e.g., 'bathymetry', 'backscatter', 'all').
        :param update: Force an update of the local FRED spatial index.
        """
        super().__init__(**kwargs)
        self.datatype = str_or(datatype.lower(), "all")
        self.force_update = update

        # Initialize the local feature registry
        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    def _parse_bbox_from_metadata(self, url: str):
        """Fetch the FGDC text metadata and extract bounding coordinates using regex."""
        response = core.Fetch(url).fetch_html()
        if response is None:
            return None

        try:
            text_content = response.text_content()
        except AttributeError:
            text_content = str(response)

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

            return mapping(box(w, s, e, n))
        except (AttributeError, ValueError) as exc:
            logger.debug(
                "[%s] Failed to parse bounding box from %s: %s", self.name, url, exc
            )
            return None

    def update_fred(self):
        """Scrape the catalog for dataset ZIPs and text metadata to build the FRED spatial index."""
        logger.info(
            "Building FRED index for USGS OFR 2014-1094. This may take a moment..."
        )

        page = core.Fetch(OFR2014_1094_CATALOG_URL).fetch_html()
        if page is None:
            logger.error("[%s] Failed to fetch OFR 2014-1094 data page.", self.name)
            return

        # Find all valid data archives (.zip)
        archive_links = sorted(
            list(
                set(
                    href
                    for href in page.xpath("//a/@href")
                    if Path(href).suffix.lower() == ".zip"
                )
            )
        )

        if not archive_links:
            logger.error(
                "[%s] No dataset archives found at %s",
                self.name,
                OFR2014_1094_CATALOG_URL,
            )
            return

        existing_ids = {
            feature.get("properties", {}).get("ID") for feature in self.FRED.features
        }

        count = 0
        with tqdm(
            total=len(archive_links),
            desc="Parsing OFR 2014-1094 Datasets",
            disable=self.silent,
        ) as pbar:
            for archive_href in archive_links:
                pbar.update()
                dataset_name = Path(archive_href).stem

                if dataset_name in existing_ids:
                    continue

                archive_url = urljoin(OFR2014_1094_CATALOG_URL, archive_href)

                # Use XPath to find the .txt link located within the same table row <tr>
                geom = None
                txt_url = None

                # Attempt 1: Look in the same table row
                txt_hrefs = page.xpath(
                    f'//a[@href="{archive_href}"]/ancestor::tr//a[contains(@href, ".txt")]/@href'
                )

                # Attempt 2: Direct substitution (common if metadata is in a separate column/folder)
                if not txt_hrefs:
                    txt_fallback = archive_href.replace(".zip", ".txt").replace(
                        "data/", "metadata/"
                    )
                    txt_url = urljoin(OFR2014_1094_CATALOG_URL, txt_fallback)
                else:
                    txt_url = urljoin(OFR2014_1094_CATALOG_URL, txt_hrefs[0])

                geom = self._parse_bbox_from_metadata(txt_url)

                # If bounding box extraction failed, fallback to general California coast extent
                if geom is None:
                    geom = mapping(box(-125.0, 32.0, -117.0, 42.0))

                # Simple heuristic for data types
                # dataset_lower = dataset_name.lower()
                dataset_lower = archive_href.lower()
                if "bathy" in dataset_lower:
                    data_type = "bathymetry"
                elif "backscatter" in dataset_lower or "bs" in dataset_lower:
                    data_type = "backscatter"
                elif "seis" in dataset_lower:
                    data_type = "seismic"
                else:
                    data_type = "vector"

                self.FRED.add_survey(
                    geom=geom,
                    Name=dataset_name,
                    ID=dataset_name,
                    Agency="USGS",
                    DataLink=archive_url,
                    MetadataLink=txt_url or OFR2014_1094_CATALOG_URL,
                    DataType=data_type,
                    DataSource=self.name,
                    Info=f"USGS OFR 2014-1094: {dataset_name}",
                )
                existing_ids.add(dataset_name)
                count += 1

        if count > 0:
            logger.info("Added %d new OFR 2014-1094 datasets to FRED.", count)
            self.FRED.save()
        else:
            logger.info("No new OFR 2014-1094 datasets were added to FRED.")

    def run(self):
        """Populate results by querying the FRED index against the requested region."""

        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info(
                "[%s] No datasets found intersecting the requested region.", self.name
            )
            return self

        for surv in results:
            data_link = surv.get("DataLink")
            dataset_id = surv.get("ID")
            data_type = surv.get("DataType", "raster")

            # Apply user-defined filtering (e.g., datatype="bathymetry")
            if self.datatype != "all":
                if (
                    self.datatype not in dataset_id.lower()
                    and self.datatype != data_type
                ):
                    continue

            if data_link:
                self.add_entry_to_results(
                    url=data_link,
                    dst_fn=Path(data_link).name,
                    data_type=data_type,
                    title=surv.get("Info"),
                    vdatum="MLLW / NAVD88",
                    hdatum="WGS84 / NAD83",
                    info=surv.get("Info"),
                )

        return self
