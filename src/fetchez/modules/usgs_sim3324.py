#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_sim3324
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Scientific Investigations Map 3324 (SIM 3324):
Colored Shaded-Relief Bathymetry, Acoustic Backscatter, and Selected Perspective
Views of the Inner Continental Borderland, Southern California.
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

SIM3324_BASE_URL = "https://pubs.usgs.gov/sim/3324/downloads/"
SIM3324_DATA_URL = f"{SIM3324_BASE_URL}sim3324_data.html"


class USGS_SIM3324(FetchModule):
    """Fetchez module to retrieve bathymetry and acoustic backscatter from USGS SIM 3324."""

    # --- Registry Metadata ---
    name = "usgs_sim3324"
    meta_category = "Bathymetry"
    meta_desc = "USGS SIM 3324: Southern California Inner Continental Borderland Bathymetry and Backscatter"
    meta_agency = "USGS"
    meta_resolution = "25 m"
    meta_license = "Public Domain"
    meta_tags = ["california", "bathymetry", "backscatter", "coastal", "usgs"]
    meta_urls = {
        "catalog": SIM3324_DATA_URL,
    }

    def __init__(self, datatype: str = "all", update: bool = False, **kwargs):
        """Initialize the USGS SIM 3324 fetch module.

        :param datatype: Filter by data type ('ascii', 'raster', 'all') or a specific
                         dataset ID (e.g., 'MV1316_25mbathy').
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
        """Scrape the catalog for datasets and text metadata to build the FRED spatial index."""
        logger.info("Building FRED index for USGS SIM 3324. This may take a moment...")

        page = core.Fetch(SIM3324_DATA_URL).fetch_html()
        if page is None:
            logger.error("[%s] Failed to fetch SIM 3324 data page.", self.name)
            return

        # Find all valid data archives (.zip or .tgz)
        archive_links = sorted(
            list(
                set(
                    href
                    for href in page.xpath("//a/@href")
                    if Path(href).suffix.lower() in (".zip", ".tgz")
                )
            )
        )

        if not archive_links:
            logger.error(
                "[%s] No dataset archives found at %s", self.name, SIM3324_DATA_URL
            )
            return

        existing_ids = {
            feature.get("properties", {}).get("ID") for feature in self.FRED.features
        }

        count = 0
        with tqdm(
            total=len(archive_links),
            desc="Parsing SIM 3324 Datasets",
            disable=self.silent,
        ) as pbar:
            for archive_href in archive_links:
                pbar.update()
                dataset_name = Path(archive_href).stem

                if dataset_name in existing_ids:
                    continue

                archive_url = urljoin(SIM3324_DATA_URL, archive_href)

                # Use XPath to find the .txt link located within the same table row <tr>
                geom = None
                txt_url = None
                txt_hrefs = page.xpath(
                    f'//a[@href="{archive_href}"]/ancestor::tr//a[contains(@href, ".txt")]/@href'
                )

                if txt_hrefs:
                    txt_url = urljoin(SIM3324_DATA_URL, txt_hrefs[0])
                    geom = self._parse_bbox_from_metadata(txt_url)

                # If bounding box extraction failed, fallback to published survey extent
                if geom is None:
                    # SIM 3324 approximate bounding box (Inner Continental Borderland)
                    geom = mapping(box(-120.0, 32.0, -117.0, 34.5))

                # Identify if it is ASCIIRaster (bathymetry) or geoTIFF (shaded relief / backscatter)
                raster_keys = ["shd", "shade", "backscatter", "persp"]
                data_type = "ascii"
                for rk in raster_keys:
                    if rk in dataset_name.lower():
                        data_type = "raster"
                        break

                self.FRED.add_survey(
                    geom=geom,
                    Name=dataset_name,
                    ID=dataset_name,
                    Agency="USGS",
                    DataLink=archive_url,
                    MetadataLink=txt_url or SIM3324_DATA_URL,
                    DataType=data_type,
                    DataSource=self.name,
                    Info=f"USGS SIM 3324: {dataset_name}",
                )
                existing_ids.add(dataset_name)
                count += 1

        if count > 0:
            logger.info("Added %d new SIM 3324 datasets to FRED.", count)
            self.FRED.save()
        else:
            logger.info("No new SIM 3324 datasets were added to FRED.")

    def run(self):
        """Populate results by querying the FRED index against the requested region."""

        # Search the local FRED geojson for datasets intersecting the requested -R region
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

            # Apply user-defined filtering (e.g., datatype="ascii" or datatype="MV1316_25mbathy")
            if self.datatype != "all":
                if self.datatype == dataset_id.lower():
                    pass  # Exact ID match
                elif self.datatype != data_type:
                    continue  # Category type mismatch

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
