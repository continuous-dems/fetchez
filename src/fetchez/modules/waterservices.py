#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.waterservices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Instantaneous Value (IV) data from USGS Water Services.

This module interfaces with the USGS National Water Information System (NWIS)
to fetch real-time or historical time-series data for sites within a region.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from urllib.parse import urlencode
from typing import Optional

from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

WATER_SERVICES_IV_URL = 'https://waterservices.usgs.gov/nwis/iv/?'

# =============================================================================
# WaterServices Module
# =============================================================================
@cli.cli_opts(
    help_text="USGS Water Services (Instantaneous Values)",
    period="Data period (ISO 8601 Duration, e.g. 'P7D' for 7 days). Default: P1D",
    parameter="Parameter Code (e.g. '00060' for Discharge, '00065' for Height). Default: All",
    sites="Specific comma-separated site numbers (ignores region if set)",
    printout="Fetch and print station summary to console immediately"
)
class WaterServices(core.FetchModule):
    """Fetch USGS Water Services data.

    Retrieves "Instantaneous Values" (IV) such as streamflow, gage height,
    and precipitation in JSON format.
    """

    def __init__(self,
                 period: str = 'P1D',
                 parameter: Optional[str] = None,
                 sites: Optional[str] = None,
                 printout: bool = False,
                 **kwargs):
        super().__init__(name='waterservices', **kwargs)
        self.period = period
        self.parameter = parameter
        self.sites = sites
        self.printout = printout


    def run(self):
        """Run the WaterServices fetch module."""

        # We need either a Region OR a list of Sites
        if self.region is None and self.sites is None:
            return []

        params = {
            'format': 'json',
            'siteStatus': 'active'
        }

        if self.period:
            params['period'] = self.period

        if self.parameter:
            params['parameterCd'] = self.parameter

        if self.sites:
            # If sites are provided, they override the bounding box
            params['sites'] = self.sites
            region_tag = "site_list"
        else:
            # USGS requires bbox: "west,south,east,north" to 6 decimal places
            w, e, s, n = self.region
            params['bBox'] = f"{w:.6f},{s:.6f},{e:.6f},{n:.6f}"
            region_tag = f"{w:.4f}_{s:.4f}"

        query_string = urlencode(params)
        full_url = f"{WATER_SERVICES_IV_URL}{query_string}"

        out_fn = f"usgs_iv_{region_tag}.json"

        self.add_entry_to_results(
            url=full_url,
            dst_fn=out_fn,
            data_type='json',
            agency='USGS',
            title='USGS Instantaneous Values',
            license='Public Domain'
        )

        # Optional Console Printout
        # Useful for quick inspections without opening the JSON file.
        if self.printout:
            self._print_station_info(full_url)

        return self


    def _print_station_info(self, url: str):
        """Fetch and print summary information for found stations."""

        logger.info(f"Querying USGS for summary: {url}")

        try:
            req = core.Fetch(url).fetch_req()
            if req is None or req.status_code != 200:
                logger.error("Failed to retrieve station info.")
                return

            data = req.json()
            time_series = data.get('value', {}).get('timeSeries', [])

            if not time_series:
                logger.info("No stations found matching criteria.")
                return

            print(f"\n{'STATION NAME':<30} | {'PARAM':<20} | {'VALUE':<10} | {'TIME'}")
            print("-" * 80)

            for item in time_series:
                try:
                    source = item.get('sourceInfo', {})
                    site_name = source.get('siteName', 'Unknown')[:28] # Truncate for display

                    variable = item.get('variable', {})
                    var_name = variable.get('variableName', 'Unknown').split(',')[0][:18]

                    values_list = item.get('values', [])
                    if values_list and values_list[0].get('value'):
                        latest_reading = values_list[0]['value'][-1] # Get last reading
                        val = latest_reading.get('value', 'N/A')
                        ts = latest_reading.get('dateTime', '')[11:16] # HH:MM
                    else:
                        val = 'N/A'
                        ts = '--:--'

                    print(f"{site_name:<30} | {var_name:<20} | {val:<10} | {ts}")

                except (KeyError, IndexError):
                    continue
            print("-" * 80 + "\n")

        except Exception as e:
            logger.error(f"Error parsing WaterServices response: {e}")
