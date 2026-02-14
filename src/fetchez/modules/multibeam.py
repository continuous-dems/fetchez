#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.multibeam
~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Multibeam bathymetry from NOAA NCEI, MBDB (ArcGIS), and R2R.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import re
import logging
import requests
from tqdm import tqdm
from io import StringIO
from typing import Optional, List, Tuple, cast

from fetchez import core
from fetchez import utils
from fetchez import spatial
from fetchez import cli

logger = logging.getLogger(__name__)

# NOAA NCEI
NCEI_DATA_URL = "https://data.ngdc.noaa.gov/platforms/"
NCEI_SEARCH_URL = "https://gis.ngdc.noaa.gov/mapviewer-support/multibeam/files.groovy?"

# MBDB (ArcGIS)
MBDB_FEATURES_URL = (
    "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_datasets/FeatureServer"
)

# R2R
R2R_API_URL = "https://service.rvdata.us/api/fileset/keyword/multibeam?"
R2R_PRODUCT_URL = "https://service.rvdata.us/api/product/?"


# =============================================================================
# Helper Functions
# =============================================================================
def _parse_mbsystem_inf_bounds(
    inf_text: StringIO,
) -> Optional[Tuple[float, float, float, float]]:
    """Parse spatial bounds from an MBSystem .inf file content."""

    minmax = [0.0, 0.0, 0.0, 0.0]  # xmin, xmax, ymin, ymax
    found = False

    for line in inf_text:
        parts = line.split()
        if len(parts) > 1 and parts[0] == "Minimum":
            try:
                if parts[1] == "Longitude:":
                    minmax[0] = utils.float_or(parts[2])  # xmin
                    minmax[1] = utils.float_or(parts[5])  # xmax
                    found = True
                elif parts[1] == "Latitude:":
                    minmax[2] = utils.float_or(parts[2])  # ymin
                    minmax[3] = utils.float_or(parts[5])  # ymax
                    found = True
            except (IndexError, ValueError):
                continue

    return cast(tuple[float, float, float, float], minmax) if found else None


# =============================================================================
# Multibeam Module (NCEI)
# =============================================================================
@cli.cli_opts(
    help_text="NOAA NCEI Multibeam Bathymetry",
    processed="Prefer processed data (v2) over raw (v1) [Default: True]",
    survey_id="Filter by specific Survey ID (e.g. KM1009)",
    ship_id="Filter by Ship ID (e.g. Kilo Moana)",
    min_year="Filter by minimum year (e.g. 2010)",
    max_year="Filter by maximum year",
    want_inf="Also download associated .inf metadata files",
)
class Multibeam(core.FetchModule):
    """Fetch multibeam bathymetric data from NOAA NCEI.

    This module queries the NCEI groovy script to find surveys intersecting
    the given region, then filters them by ship, survey, or year.
    """

    def __init__(
        self,
        processed: bool = True,
        survey_id: Optional[str] = None,
        exclude_survey_id: Optional[str] = None,
        ship_id: Optional[str] = None,
        exclude_ship_id: Optional[str] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        want_inf: bool = True,
        **kwargs,
    ):
        super().__init__(name="multibeam", **kwargs)
        self.processed_p = processed
        self.survey_id = survey_id
        self.exclude_survey_id = exclude_survey_id
        self.ship_id = ship_id
        self.exclude_ship_id = exclude_ship_id
        self.min_year = utils.float_or(min_year)
        self.max_year = utils.float_or(max_year)
        self.want_inf = want_inf

    def check_for_generated_data(self, base_url: str) -> bool:
        """Check if a 'generated' directory exists for processed data."""

        try:
            # req = core.Fetch(base_url).fetch_req()
            # if req is None or req.status_code == 404:
            parts = base_url.split("/")
            parts.insert(-1, "generated")
            gen_url = "/".join(parts)
            response = requests.head(gen_url, timeout=5, allow_redirects=True)
            if response is not None and response.status_code in [200, 302]:
                return True
            return False
        except Exception:
            return False

    def run(self):
        """Run the multibeam fetches module."""

        if self.region is None:
            return []

        w, e, s, n = self.region
        params = {"geometry": f"{w},{s},{e},{n}"}

        logger.info("Querying NCEI Multibeam database...")
        req = core.Fetch(NCEI_SEARCH_URL).fetch_req(params=params, timeout=30)

        if req is None or req.status_code != 200:
            utils.echo_error_msg(
                f"Failed to fetch multibeam request: {req.status_code if req else 'None'}"
            )
            return []

        # Parse Results
        surveys_found = {}

        lines = req.text.split("\n")
        count = 0

        for line in lines:
            if not line.strip():
                continue

            # Line format: data/../survey/ship/..
            parts = line.split(" ")[0].split("/")
            if len(parts) < 10:
                continue

            # .../platforms/ocean/mgg/multibeam/data/version/SHIP/SURVEY/...
            try:
                survey = parts[6]
                ship = parts[5]
                version = parts[9][-1]  # '1' or '2' usually
                filename = parts[-1]

                rel_path = "/".join(line.split("/")[3:]).split(" ")[0]
                data_url = f"{NCEI_DATA_URL}{rel_path}"

                date_match = re.search(r"([0-9]{8})", filename)
                date_str = date_match.group(0) if date_match else None
                year = int(date_str[:4]) if date_str else None

                if self.survey_id and survey not in self.survey_id.split("/"):
                    continue
                if self.exclude_survey_id and survey in self.exclude_survey_id.split(
                    "/"
                ):
                    continue
                if self.ship_id and ship.lower() not in [
                    x.lower() for x in self.ship_id.split("/")
                ]:
                    continue
                if self.exclude_ship_id and ship.lower() in [
                    x.lower() for x in self.exclude_ship_id.split("/")
                ]:
                    continue

                if self.min_year and year and year < self.min_year:
                    continue
                if self.max_year and year and year > self.max_year:
                    continue

                if survey not in surveys_found:
                    surveys_found[survey] = {"date": date_str, "versions": {}}

                if version not in surveys_found[survey]["versions"]:
                    surveys_found[survey]["versions"][version] = []

                local_path = filename  # flat directory structure inside survey folder
                surveys_found[survey]["versions"][version].append(
                    [data_url, local_path, "mb"]
                )
                count += 1

            except IndexError:
                continue

        if count == 0:
            logger.warning("No multibeam surveys found in region.")
            return

        logger.info(f"Found {len(surveys_found)} relevant surveys.")

        with tqdm(
            total=len(surveys_found), desc="Scanning multibeam files...", leave=False
        ) as pbar:
            for survey, data in surveys_found.items():
                versions = data["versions"]
                target_version = "2" if self.processed_p and "2" in versions else "1"
                if target_version not in versions:
                    if not self.processed_p:
                        # Add all versions
                        for v in versions:
                            self._add_version_files(versions[v])
                        continue
                    else:
                        # Dallback to v1 here.
                        continue

                # Process specific version files
                file_list = versions[target_version]
                if not file_list:
                    continue

                # Check for 'generated' directory (often holds the actual processed grids/data)
                use_generated = self.check_for_generated_data(file_list[0][0])

                final_files = []
                for f_entry in file_list:
                    url, dst, fmt = f_entry
                    if use_generated:
                        u_parts = url.split("/")
                        u_parts.insert(-1, "generated")
                        url = "/".join(u_parts)

                    final_files.append([url, dst, fmt])

                self._add_version_files(final_files)
                pbar.update()

        return self

    def _add_version_files(self, file_list: List[List[str]]):
        """Helper to add files to results."""

        for entry in file_list:
            url, dst, fmt = entry

            # Determine INF url
            base = utils.str_or(url).replace(".gz", "")
            base = utils.str_or(url).replace(".fbt", "")
            inf_url = f"{base}.inf" if not url.endswith(".inf") else url

            # Add Data File
            self.add_entry_to_results(
                url=url,
                dst_fn=dst,
                data_type=fmt,
                agency="NOAA NCEI",
                license="Public Domain",
            )

            if self.want_inf:
                # Add Metadata File
                self.add_entry_to_results(
                    url=inf_url,
                    dst_fn=dst + ".inf",
                    data_type="mb_inf",
                    agency="NOAA NCEI",
                )


# =============================================================================
# MBDB Module (ArcGIS)
# =============================================================================
@cli.cli_opts(help_text="NOAA MBDB (ArcGIS Feature Server)")
class MBDB(core.FetchModule):
    """Fetch data via the NOAA Multibeam Bathymetry Database (MBDB)
    ArcGIS Feature Server.
    """

    def __init__(
        self, where: str = "1=1", layer: int = 1, want_inf: bool = True, **kwargs
    ):
        super().__init__(name="mbdb", **kwargs)
        self.where = where
        self.want_inf = want_inf
        self._mb_features_query_url = f"{MBDB_FEATURES_URL}/{layer}/query?"

    def check_inf_region(self, mb_url: str) -> Tuple[str, Optional[Tuple]]:
        """Fetch remote .inf file and parse its region."""

        # Try finding the inf file
        src_mb = mb_url
        inf_url = f"{utils.str_or(src_mb).replace('.gz', '')}.inf"

        req = core.Fetch(inf_url).fetch_req()

        inf_region = None
        if req is not None and req.status_code == 200:
            with StringIO(req.text) as f:
                inf_region = _parse_mbsystem_inf_bounds(f)

        return inf_url, inf_region

    def run(self):
        """Run the MBDB fetching module."""

        if self.region is None:
            return []

        w, e, s, n = self.region
        params = {
            "where": self.where,
            "outFields": "*",
            "geometry": f"{w},{s},{e},{n}",
            "inSR": 4326,
            "outSR": 4326,
            "geometryType": "esriGeometryEnvelope",
            "f": "pjson",
            "returnGeometry": "false",
        }

        logger.info("Querying MBDB ArcGIS Server...")
        req = core.Fetch(self._mb_features_query_url).fetch_req(params=params)
        if req is None:
            return []

        features = req.json().get("features", [])
        logger.info(f"MBDB found {len(features)} surveys.")

        for feature in features:
            attrs = feature.get("attributes", {})
            download_url = attrs.get("DOWNLOAD_URL")

            if not download_url:
                continue

            # Scrape the download page for MB files
            # This is heavy, but necessary as MBDB only gives directory links
            page = core.Fetch(download_url).fetch_html()
            if page is None:
                continue

            # Look for /MB/ links using lxml
            mb_links = page.xpath('//a[contains(@href, "/MB/")]/@href')

            for mb in mb_links:
                # Resolve URL
                # If relative, join with download_url base.
                # Usually absolute in NCEI indexes though.
                if "http" not in mb:
                    mb = os.path.join(download_url, mb)

                # Check spatial bounds via INF to filter within the survey
                # (Since survey bbox covers entire cruise, but we only want files in our ROI)
                inf_url, inf_region = self.check_inf_region(mb)

                if inf_region and spatial.regions_intersect_p(inf_region, self.region):
                    self.add_entry_to_results(
                        url=mb,
                        dst_fn=os.path.basename(mb),
                        data_type="mbs",
                        agency="NOAA NCEI",
                        license="Public Domain",
                    )

                    if self.want_inf:
                        self.add_entry_to_results(
                            url=inf_url,
                            dst_fn=os.path.basename(inf_url),
                            data_type="mb_inf",
                            agency="NOAA NCEI",
                        )
        return self


# =============================================================================
# R2R Module
# =============================================================================
@cli.cli_opts(help_text="Rolling Deck to Repository (R2R) Multibeam")
class R2R(core.FetchModule):
    """Fetch multibeam data from the Rolling Deck to Repository (R2R) program."""

    def __init__(self, **kwargs):
        super().__init__(name="R2R", **kwargs)

    def run(self):
        """Run the R2R fetching module."""

        if self.region is None:
            return []

        # R2R expects WKT polygon
        wkt = spatial.region_to_wkt(self.region)
        params = {"spatial_bounds": wkt}

        logger.info("Querying R2R API...")
        req = core.Fetch(R2R_API_URL).fetch_req(params=params)
        if req is None:
            return []

        data = req.json().get("data", [])
        logger.info(f"R2R found {len(data)} cruises.")

        for item in data:
            cruise_id = item.get("cruise_id")
            if not cruise_id:
                continue

            # Fetch Products for Cruise
            prod_url = f"{R2R_PRODUCT_URL}cruise_id={cruise_id}"
            prod_req = core.Fetch(prod_url).fetch_req()

            if prod_req and prod_req.status_code == 200:
                products = prod_req.json().get("data", [])
                for prod in products:
                    if prod.get("datatype_name") == "Bathymetry":
                        actual_url = prod.get("actual_url")
                        if actual_url:
                            self.add_entry_to_results(
                                url=actual_url,
                                dst_fn=os.path.basename(actual_url),
                                data_type="r2rBathymetry",
                                agency="R2R",
                                license="Academic / Public",
                            )
        return self
