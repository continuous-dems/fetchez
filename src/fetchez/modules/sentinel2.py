#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.sentinel2
~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Sentinel-2 Imagery via the Copernicus Data Space Ecosystem (CDSE).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import requests
import logging
import netrc
from datetime import datetime, timedelta
from fetchez import core
from fetchez import cli
from fetchez import utils

try:
    from sentinelsat import SentinelAPI
    HAS_SENTINEL = True
except ImportError:
    HAS_SENTINEL = False

logger = logging.getLogger(__name__)

# New Copernicus Data Space Ecosystem (CDSE) Endpoints
CDSE_AUTH_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
CDSE_RESTO_URL = 'https://catalogue.dataspace.copernicus.eu/resto'
CDSE_ODATA_URL = 'https://zipper.dataspace.copernicus.eu/odata/v1'

OPENEO_URL = 'https://openeo.dataspace.copernicus.eu'
OPENEO_AUTH_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
OPENEO_API_HUB = 'https://apihub.copernicus.eu/apihub'

# =============================================================================
# Sentinel-2 Module
# =============================================================================
@cli.cli_opts(
    help_text="Copernicus Sentinel-2 Imagery (via CDSE)",
    start_date="Start Date (YYYY-MM-DD)",
    end_date="End Date (YYYY-MM-DD)",
    cloud_cover="Max Cloud Cover % (0-100). Default: 20",
    product_type="Product Level (S2MSI1C, S2MSI2A). Default: S2MSI2A"
)

class Sentinel2(core.FetchModule):
    """Fetch Sentinel-2 optical satellite imagery.

    This module queries the Copernicus Data Space Ecosystem (CDSE).
    It requires a CDSE account (email/password) stored in your ~/.netrc file.

    Machine: identity.dataspace.copernicus.eu
    Login: <your_email>
    Password: <your_password>

    **Dependencies:**
    - `sentinelsat`: Required for query parsing (`pip install sentinelsat`)

    References:
      - https://dataspace.copernicus.eu/
    """

    def __init__(self,
                 start_date: str = None,
                 end_date: str = None,
                 cloud_cover: int = 20,
                 product_type: str = 'S2MSI2A',
                 **kwargs):
        super().__init__(name='sentinel2', **kwargs)
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = int(cloud_cover)
        self.product_type = product_type


    def _get_token(self, username, password):
        """Generate an OAuth2 Access Token from CDSE Keycloak."""

        try:
            payload = {
                'client_id': 'cdse-public',
                'username': username,
                'password': password,
                'grant_type': 'password'
            }
            r = requests.post(CDSE_AUTH_URL, data=payload, timeout=10)
            r.raise_for_status()
            return r.json().get('access_token')
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return None

    def run(self):
        """Run the Sentinel-2 fetching logic."""

        if self.region is None:
            return []

        if not HAS_SENTINEL:
            logger.error("This module requires 'sentinelsat'. Install via: pip install sentinelsat")
            return self

        username, password = core.get_userpass(CDSE_AUTH_URL)
        if not username or not password:
            logger.error(f"No credentials found for {CDSE_AUTH_URL} in ~/.netrc")
            logger.info("Please add 'machine identity.dataspace.copernicus.eu login <email> password <pw>' to .netrc")
            return self

        logger.info("Authenticating with Copernicus Data Space...")
        token = self._get_token(username, password)
        if not token:
            return self

        self.headers['Authorization'] = f"Bearer {token}"

        try:
            api = SentinelAPI(username, password, CDSE_RESTO_URL)

            if not self.start_date:
                self.start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            else:
                self.start_date = self.start_date.replace('-', '')

            if not self.end_date:
                self.end_date = datetime.now().strftime('%Y%m%d')
            else:
                self.end_date = self.end_date.replace('-', '')

            w, e, s, n = self.region
            footprint = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

            logger.info(f"Querying Sentinel-2 ({self.product_type})...")

            products = api.query(
                footprint,
                date=(self.start_date, self.end_date),
                platformname='Sentinel-2',
                producttype=self.product_type,
                cloudcoverpercentage=(0, self.cloud_cover)
            )

            df = api.to_dataframe(products)
            logger.info(f"Found {len(df)} scenes.")

            for uuid, row in df.iterrows():
                title = row['title']

                download_url = f"{CDSE_ODATA_URL}/Products({uuid})/$value"

                self.add_entry_to_results(
                    url=download_url,
                    dst_fn=f"{title}.zip",
                    data_type='sentinel2',
                    agency='ESA / Copernicus',
                    title=title
                )

        except Exception as e:
            logger.error(f"Sentinel-2 Query Error: {e}")

        return self


    def run_openeo(self):
        """Run the OpenEO fetching module"""

        username, password = fetches.get_userpass(OPENEO_AUTH_URL)
        api = SentinelAPI(username, password, OPENEO_API_HUB)

        # Define your area of interest (e.g., from a GeoJSON file)
        #footprint = geojson_to_wkt(read_geojson('/path/to/your/area_of_interest.geojson'))

        w, e, s, n = self.region
        footprint = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

        # Query for Sentinel-2 products
        products = api.query(footprint,
                             date=('20230101', date(2023, 1, 31)),
                             platformname='Sentinel-2',
                             cloudcoverpercentage=(0, 20)) # Max 20% cloud cover

        # Download all found products
        api.download_all(products)

        return(self)

### End
