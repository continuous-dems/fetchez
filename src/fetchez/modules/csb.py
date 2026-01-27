#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.csb
~~~~~~~~~~~~~~~~~~~~

Fetch Crowd Sourced Bathymetry (CSB) from NOAA.

This module indexes CSB metadata via the NOAA 'Crowbar' API and 
downloads the raw CSV point files directly from the AWS S3 Open Data bucket.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from typing import Optional, Dict, List
from urllib.parse import urlparse

from fetchez import core
from fetchez import spatial
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

CROWBAR_SEARCH_URL = "https://www.ngdc.noaa.gov/ingest-external/index-service/api/v1/csb/index?"
S3_BASE_URL = "https://noaa-dcdb-bathymetry-pds.s3.amazonaws.com"

# =============================================================================
# CSB Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA Crowd Sourced Bathymetry (Direct S3)",
    min_year="Filter by minimum year (e.g. 2020)",
    max_year="Filter by maximum year (e.g. 2023)",
    platform="Filter by Platform Name (exact match)",
    provider="Filter by Provider Name (exact match)",
    limit="Max number of files to fetch (default: 2000)"
)

class CSB(core.FetchModule):
    """Fetch Crowd Sourced Bathymetry (CSB) data.
    
    Instead of waiting for a server-side aggregation, this module:
    - Searches the NOAA Crowbar Index for files in your region.
    - Generates direct download links to the raw CSVs on S3.
    - Downloads them in parallel.
    """
    
    def __init__(self, 
                 min_year: Optional[int] = None,
                 max_year: Optional[int] = None,
                 platform: Optional[str] = None,
                 provider: Optional[str] = None,
                 limit: int = 2000,
                 **kwargs):
        super().__init__(name='csb', **kwargs)
        self.min_year = min_year
        self.max_year = max_year
        self.platform = platform
        self.provider = provider
        self.limit = limit

        
    def run(self):
        """Run the CSB fetches module."""
        
        if self.region is None:
            return []

        w, e, s, n = self.region
        aoi = spatial.region_to_wkt(self.region)
        
        page_size = min(self.limit, 200)
        
        params = {
            #'bbox': f"{w},{s},{e},{n}",
            'aoi': aoi,
            'itemsPerPage': page_size,
        }
        
        # Add filters
        if self.min_year: params['from'] = f"{self.min_year}-01-01"
        if self.max_year: params['to'] = f"{self.max_year}-12-31"
        if self.platform: params['platform'] = self.platform
        if self.provider: params['provider'] = self.provider

        logger.info("Querying NOAA Crowbar Index...")

        total_fetched = 0
        page = 1        
        while total_fetched < self.limit:
            params['page'] = page
            
            req = core.Fetch(CROWBAR_SEARCH_URL).fetch_req(params=params)
            if req is None or req.status_code != 200:
                logger.error(f"Failed to query CSB index (Page {page}).")
                break

            try:
                data = req.json()
                items = data.get('items', [])
                total_count = data.get('totalItems', 0)
                total_pages = data.get('totalPages', 0)
                
                if page == 1:
                    logger.info(f"Total files available in region: {total_count} items in {total_pages} pages")

            except Exception as e:
                logger.error(f"Failed to parse index response: {e}")
                break
                
            if not items:
                break

            for item in items:
                if total_fetched >= self.limit:
                    break

                locations = item.get('otherLocations', {})
                s3_key = locations.get('s3')
                if not s3_key: continue

                try:
                    parsed_s3 = urlparse(s3_key)
                    relative_path = parsed_s3.path
                    url = f"{S3_BASE_URL.rstrip('/')}/{relative_path.lstrip('/')}"
                    
                    filename = os.path.basename(s3_key)
                    plat = item.get('platform', 'Unknown')
                    date = item.get('collectionDate', '')[:10]
                    
                    self.add_entry_to_results(
                        url=url,
                        dst_fn=filename,
                        data_type='csb_csv',
                        agency='NOAA NCEI',
                        title=f"CSB: {plat}",
                        date=date,
                        license='CC0 / Public Domain'
                    )
                    total_fetched += 1
                except Exception:
                    continue

            if total_fetched >= total_count:
                break
                
            page += 1

        if total_fetched >= self.limit and total_fetched < total_count:
            logger.warning(f"Hit limit of {self.limit} files. (Total available: {total_count})")
        else:
            logger.info(f"Queued {total_fetched} files for download.")

        return self
