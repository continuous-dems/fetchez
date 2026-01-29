#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.buoys
~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA National Data Buoy Center (NDBC) data.

This module searches for buoys within a given region (using a radial search
from the center) or by specific station ID. It can fetch both realtime 
standard meteorological data and historical archives.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import datetime
import lxml.html
from typing import Optional, List, Set

from fetchez import core
from fetchez import spatial
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

NDBC_URL = 'https://www.ndbc.noaa.gov'
BUOY_RADIAL_SEARCH_URL = 'https://www.ndbc.noaa.gov/radial_search.php'
BUOY_REALTIME_URL = 'https://www.ndbc.noaa.gov/data/realtime2/'
BUOY_HISTORICAL_URL = 'https://www.ndbc.noaa.gov/data/historical/stdmet/'

# =============================================================================
# Buoys Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA NDBC Buoy Data",
    station_id="Specific Buoy Station ID (comma-separated for multiple)",
    radius="Search radius in Nautical Miles (default: 100)",
    datatype="Data type: 'realtime' (last 45 days) or 'historical' (archives) [Default: realtime]",
    min_year="Start year for historical data (default: 2010)",
    max_year="End year for historical data (default: current year)"
)
class Buoys(core.FetchModule):
    """Fetch NOAA Buoy Data (NDBC).
    
    Can fetch "Realtime" (txt) or "Historical" (gz) standard meteorological data.
    If no station_id is provided, it performs a radial search from the 
    center of the input region.
    """
    
    def __init__(self, 
                 station_id: Optional[str] = None, 
                 radius: int = 100,
                 datatype: str = 'realtime',
                 min_year: int = 2010,
                 max_year: Optional[int] = None,
                 **kwargs):
        super().__init__(name='buoys', **kwargs)
        self.station_id = station_id
        self.radius = radius
        self.datatype = datatype.lower()
        self.min_year = min_year
        self.max_year = max_year if max_year else datetime.datetime.now().year

        
    def _get_stations_from_region(self) -> Set[str]:
        """Perform radial search to find stations in the region."""
        
        if not self.region:
            return set()

        # Calculate center
        center_lon, center_lat = spatial.region_center(self.region)
        
        # NDBC Params
        # uom=E (English/Nautical Miles), uom=M (Metric/km)
        # ot=A (Observation Time: All)
        params = {
            'lat1': center_lat,
            'lon1': center_lon,
            'uom': 'E',    
            'ot': 'A',     
            'dist': self.radius,
            'time': 0,
        }
        
        logger.info(f"Searching for buoys within {self.radius}nm of ({center_lat:.2f}, {center_lon:.2f})...")
        
        req = core.Fetch(BUOY_RADIAL_SEARCH_URL).fetch_req(params=params)
        if req is None or req.status_code != 200:
            logger.error("Failed to query NDBC search.")
            return set()

        stations = set()
        try:
            doc = lxml.html.fromstring(req.content)
            # Links to stations should look like station_page.php?station=44008
            links = doc.xpath('//a[contains(@href, "station=")]/@href')
            
            for href in links:
                if 'station=' in href:
                    sid = href.split('station=')[-1].split('&')[0].upper()
                    stations.add(sid)
                    
        except Exception as e:
            logger.error(f"Failed to parse buoy search results: {e}")

        return stations

    def run(self):
        """Run the Buoys fetcher."""
        
        target_stations = set()
        
        # Determine Target Stations
        if self.station_id:
            # User provided explicit IDs
            for s in self.station_id.split(','):
                target_stations.add(s.strip().upper())
        elif self.region:
            # Search by Region
            target_stations = self._get_stations_from_region()
        else:
            return []

        if not target_stations:
            logger.info("No buoys found matching criteria.")
            return self

        logger.info(f"Processing {len(target_stations)} stations...")

        # Generate URLs
        for sid in target_stations:
            
            # --- Realtime Data ---
            if 'realtime' in self.datatype:
                # Standard Meteorological Data
                # URL: https://www.ndbc.noaa.gov/data/realtime2/44008.txt
                url = f"{BUOY_REALTIME_URL}{sid}.txt"
                self.add_entry_to_results(
                    url=url,
                    dst_fn=f"{sid}_realtime.txt",
                    data_type='buoy_txt',
                    agency='NOAA NDBC',
                    title=f"Buoy {sid} Realtime",
                    license='Public Domain'
                )

            # --- Historical Data ---
            if 'historical' in self.datatype:
                # Historical Standard Met Data
                # URL: https://www.ndbc.noaa.gov/data/historical/stdmet/44008h2021.txt.gz
                
                for yr in range(self.min_year, self.max_year + 1):
                    # Filename format: {sid}h{year}.txt.gz
                    filename = f"{sid.lower()}h{yr}.txt.gz"
                    url = f"{BUOY_HISTORICAL_URL}{filename}"
                    
                    self.add_entry_to_results(
                        url=url,
                        dst_fn=filename,
                        data_type='buoy_hist_gz',
                        agency='NOAA NDBC',
                        date=str(yr),
                        title=f"Buoy {sid} {yr}",
                        license='Public Domain'
                    )

        return self
