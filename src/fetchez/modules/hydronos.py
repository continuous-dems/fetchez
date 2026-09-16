#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.hydronos
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch NOS Hydrographic Surveys (BAGs and XYZ soundings) from NOAA.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging
from typing import Optional, Dict

from fetchez import core
from fetchez.modules import FetchModule
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

# Depreciated
# NOS_DYNAMIC_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/nos_hydro_dynamic/MapServer"
NOS_DYNAMIC_URL = "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/NOS_Hydro_Surveys/FeatureServer"
NOS_DATA_URL = "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/"


# =============================================================================
# HydroNOS Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA NOS Hydrographic Surveys (BAG & XYZ)",
    datatype='Data type to fetch: "bag" (Bathymetric Attributed Grid) or "xyz" (Soundings)',
    layer="ArcGIS Layer ID: 0 (All Soundings) [Default: 0]",
    survey_id="Filter by specific Survey ID (e.g. H12345)",
    min_year="Filter by minimum survey year",
    max_year="Filter by maximum survey year",
)
class HydroNOS(FetchModule):
    name = "nos_hydro"
    meta_category = "Bathymetry"
    meta_desc = "NOAA NOS Hydrographic Surveys (BAG & XYZ)"
    meta_agency = "NOAA NOS"
    meta_tags = ["bathymetry", "hydrography", "nos", "noaa", "bag", "soundings"]
    meta_region = "USA / Coastal"
    meta_resolution = "Varies (0.5m - 30m)"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://www.ngdc.noaa.gov/mgg/bathymetry/hydro.html"}

    """Fetch NOAA National Ocean Service (NOS) Hydrographic Surveys.

    This module queries the NOS Hydrographic Data Base (NOSHDB).
    """

    def __init__(
        self,
        where: str = "1=1",
        layer: int = 0,
        datatype: Optional[str] = None,
        survey_id: Optional[str] = None,
        exclude_survey_id: Optional[str] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(name="hydronos", **kwargs)
        self.where = where
        self.datatype = datatype
        self.layer = utils.int_or(layer, 0)
        self.survey_id = survey_id
        self.exclude_survey_id = exclude_survey_id
        self.min_year = utils.float_or(min_year)
        self.max_year = utils.float_or(max_year)

        self._nos_query_url = f"{NOS_DYNAMIC_URL}/{self.layer}/query?"

    def run(self):
        """Run the hydronos fetches module."""

        if self.wgs_region is None:
            return []

        w, e, s, n = self.wgs_region

        # Prepare ArcGIS Query
        params = {
            "where": self.where,
            "outFields": "*",
            "geometry": f"{w},{s},{e},{n}",
            "inSR": 4326,
            "outSR": 4326,
            "f": "pjson",
            "returnGeometry": "false",
        }

        logger.debug(f"Querying NOS Hydro (Layer {self.layer})...")
        req = core.Fetch(self._nos_query_url).fetch_req(params=params)

        if req is None:
            return self
        try:
            response = req.json()
        except json.JSONDecodeError:
            logger.error("Failed to parse HydroNOS response.")
            return self

        features = response.get("features", [])
        logger.debug(f"Found {len(features)} HydroNOS surveys.")

        for feature in features:
            attrs = feature.get("attributes", {})

            # Filter by Year
            year_val = attrs.get("SURVEY_YEAR")
            try:
                year = utils.int_or(year_val, 0)
            except ValueError:
                year = 0

            if self.min_year is not None and year < self.min_year:
                continue
            if self.max_year is not None and year > self.max_year:
                continue

            # Process Download Links
            self._process_download(attrs, year)

        return self

    def _process_download(self, attrs: Dict, year: int):
        """Process download URL."""

        survey_id = attrs.get("SURVEY_ID")
        download_url = attrs.get("DOWNLOAD_URL")

        if not download_url:
            return

        # Filter by Survey ID
        if self.survey_id:
            if survey_id not in self.survey_id.split("/"):
                return

        if self.exclude_survey_id:
            if survey_id in self.exclude_survey_id.split("/"):
                return

        # Construct Base Data Link
        try:
            # Extract the range folder (e.g. H12001-H14000) from the API url
            nos_dir = download_url.split("/")[-2]
            data_link = f"{NOS_DATA_URL}{nos_dir}/{survey_id}/"
        except IndexError:
            # Fallback to the link provided
            data_link = download_url
            if not data_link.endswith("/"):
                data_link += "/"

        # Fetch BAGs (Bathymetric Attributed Grids)
        if self.datatype is None or "bag" in self.datatype.lower():
            bags_exist = str(attrs.get("BAGS_EXIST", "")).upper()

            if bags_exist in ["TRUE", "Y", "YES"]:
                bag_dir_url = f"{data_link}BAG/"

                # Scrape the directory for .bag files
                bag_page = core.Fetch(bag_dir_url).fetch_html()

                if bag_page is not None:
                    bags = bag_page.xpath('//a[contains(@href, ".bag")]/@href')
                    for bag in bags:
                        # Sometimes href is relative, sometimes full
                        url = bag if "http" in bag else f"{bag_dir_url}{bag}"

                        self.add_entry_to_results(
                            url=url,
                            dst_fn=os.path.basename(bag),
                            data_type="bag",
                            agency="NOAA NOS",
                            date=str(year),
                            license="Public Domain",
                        )

        # Fetch XYZ (GEODAS Soundings)
        if self.datatype is None or "xyz" in self.datatype.lower():
            # Check for GEODAS folder or files
            xyz_page = core.Fetch(data_link).fetch_html()

            if xyz_page is not None:
                # Look for GEODAS folder
                geodas_links = xyz_page.xpath('//a[contains(@href, "GEODAS")]/@href')

                if geodas_links:
                    # Construct standard filenames
                    xyz_filename = f"{survey_id}.xyz.gz"
                    xyz_link = f"{data_link}GEODAS/{xyz_filename}"

                    # Default to meters
                    dt = "nos-xyz"
                    # survey_year = int(year) if year else 2000

                    # Can't really tell what units hydronos data is in,
                    # especially pre-1970
                    # # Only check for the htm file on older surveys
                    # if survey_year < 1970:
                    #     htm_link = f"{data_link}GEODAS/{survey_id}_h93.htm"
                    #     htm_page = core.Fetch(htm_link).fetch_html()

                    #     if htm_page is not None:
                    #         page_text = htm_page.text_content().upper()
                    #         if "FEET" in page_text:
                    #             dt = "nos-feet-xyz"
                    #         elif "FATHOMS" in page_text:
                    #             dt = "nos-fathoms-xyz"
                    #     else:
                    #         if survey_year < 1960:
                    #             dt = "nos-feet-xyz"

                    # Verify the data file exists (HEAD request)
                    if core.Fetch(xyz_link).fetch_req(timeout=5) is not None:
                        self.add_entry_to_results(
                            url=xyz_link,
                            dst_fn=xyz_filename,
                            data_type=dt,
                            agency="NOAA NOS",
                            date=str(year),
                            license="Public Domain",
                        )
                # if geodas_links:
                #     # Construct standard filename: {SURVEY}.xyz.gz
                #     # This is faster than scraping the subdirectory if naming is consistent
                #     xyz_filename = f"{survey_id}.xyz.gz"
                #     xyz_link = f"{data_link}GEODAS/{xyz_filename}"

                #     survey_year = int(year) if year else 2000
                #     dt = "nos-feet-xyz" if survey_year < 1960 else "nos-xyz"

                #     # Verify it exists (HEAD request)
                #     if core.Fetch(xyz_link).fetch_req(timeout=5) is not None:
                #         self.add_entry_to_results(
                #             url=xyz_link,
                #             dst_fn=xyz_filename,
                #             data_type=dt,
                #             agency="NOAA NOS",
                #             date=str(year),
                #             license="Public Domain",
                #         )
        if self.datatype is None or "grid" in self.datatype.lower():
            bags_exist = str(attrs.get("BAGS_EXIST", "")).upper()
            if bags_exist not in ["TRUE", "Y", "YES"]:  # and self.datatype is not None:
                # Check for Grid_Data folder or files
                xyz_page = core.Fetch(data_link).fetch_html()

                if xyz_page is not None:
                    gridded_links = xyz_page.xpath(
                        '//a[contains(@href, "Gridded_Data")]/@href'
                    )
                    if gridded_links:
                        gridded_page = core.Fetch(
                            f"{data_link}Gridded_Data/"
                        ).fetch_html()
                        xyz_links = gridded_page.xpath(
                            '//a[contains(@href, ".gz")]/@href'
                        )
                        for xyz_filename in xyz_links:
                            xyz_link = f"{data_link}Gridded_Data/{xyz_filename}"
                            dt = "nos-gridded"

                            # Verify the data file exists (HEAD request)
                            if core.Fetch(xyz_link).fetch_req(timeout=5) is not None:
                                self.add_entry_to_results(
                                    url=xyz_link,
                                    dst_fn=xyz_filename,
                                    data_type=dt,
                                    agency="NOAA NOS",
                                    date=str(year),
                                    license="Public Domain",
                                )
