#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tides
~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA Tides & Currents data (CO-OPS).

Supports two modes:
1. Station Discovery (Spatial): Find stations within a bounding box.
2. Data Retrieval (Station ID): Fetch time-series data (water levels, predictions).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from urllib.parse import urlencode
from datetime import datetime, timedelta
from fetchez import core
from fetchez import cli
from fetchez import utils

# Service for finding stations (ArcGIS REST)
STATION_SEARCH_URL = "https://mapservices.weather.noaa.gov/static/rest/services/NOS_Observations/CO_OPS_Products/FeatureServer/0/query?"

# Service for fetching data (CO-OPS API)
DATA_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"


# =============================================================================
# Tides Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA CO-OPS Tides & Currents",
    station="Station ID (e.g. 8518750). If provided, fetches DATA. If omitted, searches REGION.",
    start_date="Start Date (YYYYMMDD). Required for data mode.",
    end_date="End Date (YYYYMMDD). Required for data mode.",
    datum="Vertical Datum (MLLW, MSL, NAVD88, STND). Default: MLLW",
    product="Product (water_level, predictions, air_temperature, wind). Default: water_level",
    interval="Data Interval (h, hilo). Default: h (Hourly) for data, None for 6-min.",
)
class Tides(core.FetchModule):
    """Fetch NOAA Tides & Currents data.

    Mode: Station Discovery (Default if -R provided, --station omitted)
      Searches the provided region for active tide stations and saves a GeoJSON list.

    Mode: Data Retrieval (Default if --station provided)
      Downloads time-series data for the specific station.

    References:
      - https://tidesandcurrents.noaa.gov/
      - https://api.tidesandcurrents.noaa.gov/api/prod/
    """

    def __init__(
        self,
        station: str = None,
        start_date: str = None,
        end_date: str = None,
        datum: str = "MLLW",
        product: str = "water_level",
        interval: str = None,
        **kwargs,
    ):
        super().__init__(name="tides", **kwargs)
        self.station = station
        self.start_date = start_date
        self.end_date = end_date
        self.datum = datum
        self.product = product
        self.interval = interval

    def _run_station_search(self):
        """Search for stations in the region."""

        if self.region is None:
            return

        w, e, s, n = self.region

        params = {
            "outFields": "*",
            "units": "esriSRUnit_Meter",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": 4326,
            "outSR": 4326,
            "f": "geojson",
        }

        full_url = f"{STATION_SEARCH_URL}{urlencode(params)}"

        r_str = f"w{w}_e{e}_s{s}_n{n}".replace(".", "p").replace("-", "m")
        out_fn = f"tides_stations_{r_str}.geojson"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="geojson",
            agency="NOAA CO-OPS",
            title="Tide Stations List",
        )

    def _run_data_fetch(self):
        """Fetch time-series data for a station."""
        if not self.start_date or not self.end_date:
            # Default to last 24 hours if not specified
            now = datetime.utcnow()
            if not self.end_date:
                self.end_date = now.strftime("%Y%m%d")
            if not self.start_date:
                self.start_date = (now - timedelta(days=1)).strftime("%Y%m%d")

        params = {
            "station": self.station,
            "begin_date": self.start_date,
            "end_date": self.end_date,
            "product": self.product,
            "datum": self.datum,
            "units": "metric",
            "time_zone": "gmt",
            "application": "Fetchez",
            "format": "csv",
        }

        # Interval handling (Standard is 6-min, 'h' is hourly)
        if self.interval:
            params["interval"] = self.interval

        full_url = f"{DATA_API_URL}{urlencode(params)}"

        # Output: tides_8518750_water_level_20230101_20230107.csv
        out_fn = (
            f"tides_{self.station}_{self.product}_{self.start_date}_{self.end_date}.csv"
        )

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type="csv",
            agency="NOAA CO-OPS",
            title=f"Station {self.station} Data",
        )

    def run(self):
        """Run the TIDES fetching module."""

        if self.station:
            self._run_data_fetch()
        elif self.region:
            self._run_station_search()

        return self
