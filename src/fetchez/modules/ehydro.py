#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.ehydro
~~~~~~~~~~~~~~~~~~~~~~

Fetch USACE eHydro bathymetric survey data.

:copyright: (c) 2013 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import json
import logging
import datetime
from urllib.parse import urlencode
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

# USACE eHydro Feature Service
EHYDRO_BASE_URL = "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/eHydro_Survey_Data/FeatureServer/0/query"


# =============================================================================
# eHydro Module
# =============================================================================
@cli.cli_opts(
    help_text="USACE eHydro (Bathymetry)",
    where="SQL filter clause (default: '1=1')",
    survey="Filter by survey name/ID (substring match)",
    min_year="Filter surveys after this year (YYYY)",
    max_year="Filter surveys before this year (YYYY)",
)
class eHydro(core.FetchModule):
    """Fetch USACE eHydro bathymetric data.

    The eHydro dataset supports the USACE navigation mission by providing
    bathymetric survey data for navigation channels and harbors.

    The module queries the ArcGIS REST API to find survey extents that
    intersect the given region and downloads the associated data files
    (often ZIPs containing XYZ/GeoTIFFs).

    References:
      - https://navigation.usace.army.mil/Survey/Hydro
    """

    def __init__(
        self,
        where: str = "1=1",
        survey: str = None,
        min_year: str = None,
        max_year: str = None,
        **kwargs,
    ):
        super().__init__(name="ehydro", **kwargs)
        self.where = where
        self.survey_filter = survey
        self.min_year = int(min_year) if min_year else None
        self.max_year = int(max_year) if max_year else None

    def _parse_year(self, timestamp):
        """Safely parse ESRI timestamp (milliseconds) to year."""

        try:
            if timestamp is None:
                return None
            # Handle milliseconds
            seconds = int(str(timestamp)[:10])
            dt = datetime.datetime.fromtimestamp(seconds)
            return dt.year
        except (ValueError, TypeError):
            return None

    def run(self):
        """Run the eHydro fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        params = {
            "where": self.where,
            "outFields": "*",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "f": "json",
            "returnGeometry": "false",
        }

        query_url = f"{EHYDRO_BASE_URL}?{urlencode(params)}"
        logger.info("Querying USACE eHydro API...")

        req = core.Fetch(query_url).fetch_req()
        if not req or req.status_code != 200:
            logger.error("Failed to query eHydro API.")
            return self

        try:
            response = req.json()
        except json.JSONDecodeError:
            logger.error("Failed to parse eHydro JSON response.")
            return self

        features = response.get("features", [])
        if not features:
            logger.warning("No eHydro surveys found in this region.")
            return self

        logger.info(f"Scanning {len(features)} potential surveys...")

        matches = 0
        for feature in features:
            attrs = feature.get("attributes", {})

            # Attributes of interest
            sid = attrs.get("sdsmetadataid", "Unknown")
            url = attrs.get("sourcedatalocation")
            survey_date_ts = attrs.get("surveydatestart")

            if not url:
                continue

            year = self._parse_year(survey_date_ts)
            if self.min_year and year and year < self.min_year:
                continue
            if self.max_year and year and year > self.max_year:
                continue

            if self.survey_filter:
                if self.survey_filter.lower() not in sid.lower():
                    continue

            fname = url.split("/")[-1]
            if "?" in fname:
                fname = fname.split("?")[0]

            self.add_entry_to_results(
                url=url,
                dst_fn=fname,
                data_type="bathymetry",
                agency="USACE",
                title=f"Survey {sid} ({year})",
            )
            matches += 1

        logger.info(f"Found {matches} surveys matching criteria.")
        return self
