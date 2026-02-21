#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.cdse
~~~~~~~~~~~~~~~~~~~~

Fetch specific bands (e.g., Sentinel-2 JP2 files) directly from the
Copernicus Data Space Ecosystem (CDSE) using OData and internal nodes.

:copyright: (c) 2025 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import requests
import datetime
import time
import re
import logging
import xml.etree.ElementTree as ET

from fetchez import core
from fetchez import cli
from fetchez import utils

logger = logging.getLogger(__name__)

CDSE_CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
CDSE_AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


@cli.cli_opts(
    help_text="CDSE Direct Node Fetcher (Sentinel-2 JP2 Bands)",
    collection_name="Collection (e.g., SENTINEL-2). Default: SENTINEL-2",
    product_type="Product Type (e.g., S2MSI1C, S2MSI2A). Default: S2MSI1C",
    cloud_cover="Max cloud cover percentage (0-100)",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
)
class CDSE(core.FetchModule):
    """Copernicus Data Space Ecosystem Fetch Module

    Fetches individual satellite imagery bands directly from CDSE Nodes.
    Requires a valid CDSE account in your ~/.netrc file.
    """

    def __init__(
        self,
        collection_name="SENTINEL-2",
        product_type="S2MSI1C",
        cloud_cover=None,
        start_date="",
        end_date="",
        **kwargs,
    ):

        self._headers = {}
        self._token_expiry = 0.0

        super().__init__(name="cdse", **kwargs)

        self.collection_name = collection_name
        self.product_type = product_type
        self.max_cloud_cover = utils.float_or(cloud_cover)

        w, e, s, n = self.region
        self.aoi = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

        # Format Timestamps (Default to One year ago -> Today)
        if not end_date:
            end_date = datetime.datetime.now().isoformat()
        if not start_date:
            start_date = (
                datetime.datetime.now() - datetime.timedelta(days=365)
            ).isoformat()

        self.time_start = self._format_date(start_date)
        self.time_end = self._format_date(end_date)

        # Initial Authentication
        self.access_token = self.refresh_token()

    @property
    def headers(self):
        """Dynamic headers property that checks for token expiry before every request."""

        # Buffer of 30 seconds to ensure we don't expire mid-request
        if time.time() > (self._token_expiry - 30):
            logger.debug("CDSE Token expired or expiring soon. Refreshing...")
            self.refresh_token()
        return self._headers

    @headers.setter
    def headers(self, value):
        self._headers = value

    def refresh_token(self):
        """Acquire a new token and update headers/expiry."""

        username, password = core.get_userpass(CDSE_AUTH_URL)
        if not username:
            username, password = core.get_userpass("dataspace.copernicus.eu")

        if not username or not password:
            logger.warning("No credentials found in .netrc for CDSE.")
            return None

        data = {
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        }

        try:
            response = requests.post(CDSE_AUTH_URL, data=data)
            response.raise_for_status()
            json_resp = response.json()

            token = json_resp.get("access_token")
            expires_in = json_resp.get("expires_in", 600)

            self.access_token = token
            # Set expiry time (current time + lifetime)
            self._token_expiry = time.time() + int(expires_in)
            self._headers = {"Authorization": f"Bearer {token}"}

            logger.info(
                f"Successfully retrieved CDSE access token (expires in {expires_in}s)."
            )
            return token

        except requests.exceptions.RequestException as e:
            logger.error(f"CDSE Authentication failed: {e}")
            self._headers = {}
            return None

    def _format_date(self, date_str: str) -> str:
        """Formats an ISO date string for the OData filter."""

        if not date_str:
            return ""
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", ""))
            return dt.isoformat(timespec="milliseconds") + "Z"
        except ValueError:
            return ""

    def _resolve_redirects(self, initial_url: str) -> str:
        """Manually resolve redirects to get the final download URL."""

        url = initial_url
        for _ in range(10):
            # We use HEAD to resolve redirects without downloading the payload
            req = requests.head(url, headers=self.headers, allow_redirects=False)
            if req.status_code in (301, 302, 303, 307):
                url = req.headers["Location"]
            else:
                break
        return url

    def _strip_ns(self, xml_text):
        """Strip namespaces from XML string to allow simple tag searching."""

        # return re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)
        return re.sub(r"\sxmlns='[^']+'", "", xml_text, count=1)

    def run(self):
        """Execute the query and generate download links for JP2 bands."""

        if not self.aoi or not self.access_token:
            return self

        filters = [
            f"Collection/Name eq '{self.collection_name}'",
            f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq '{self.product_type}')",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{self.aoi}')",
        ]

        if self.time_start:
            filters.append(f"ContentDate/Start gt {self.time_start}")

        if self.time_end:
            filters.append(f"ContentDate/Start lt {self.time_end}")

        if self.max_cloud_cover is not None:
            filters.append(
                f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {self.max_cloud_cover})"
            )

        # Initial query URL
        query_url = (
            f"{CDSE_CATALOGUE_URL}/Products?$filter={' and '.join(filters)}&$top=100"
        )

        logger.info(f"Querying CDSE Catalogue: {query_url}")
        page_count = 0

        while query_url:
            page_count += 1
            logger.info(f"Fetching metadata page {page_count}...")

            try:
                response_req = requests.get(query_url)
                response_req.raise_for_status()
                response = response_req.json()
            except Exception as e:
                logger.error(f"Error querying CDSE Catalogue: {e}")
                break

            results = response.get("value", [])
            if not results:
                break

            for result in results:
                try:
                    product_id = result["Id"]
                    product_name = result["Name"]

                    # Resolve redirect to actual node storage
                    meta_url = f"{CDSE_CATALOGUE_URL}/Products({product_id})/Nodes({product_name})/Nodes(MTD_MSIL1C.xml)/$value"
                    final_meta_url = self._resolve_redirects(meta_url)

                    # Fetch the XML Metadata
                    meta_req = requests.get(final_meta_url, headers=self.headers)
                    if meta_req.status_code != 200:
                        continue

                    # Parse XML for Band paths
                    xml_content = self._strip_ns(meta_req.text)
                    root = ET.fromstring(xml_content.encode("utf-8"))

                    image_files = root.findall(".//IMAGE_FILE")
                    # We are only interested in RGB for visual checking (B02, B03, B04)
                    target_bands = [
                        img.text
                        for img in image_files
                        if img.text
                        and (
                            img.text.endswith("B02")
                            or img.text.endswith("B03")
                            or img.text.endswith("B04")
                        )
                    ]

                    # Register each band as a distinct download entry
                    for band_path in target_bands:
                        parts = band_path.split("/")
                        parts[-1] = f"{parts[-1]}.jp2"
                        node_path = "/".join([f"Nodes({p})" for p in parts])
                        file_url = f"{CDSE_CATALOGUE_URL}/Products({product_id})/Nodes({product_name})/{node_path}/$value"

                        self.add_entry_to_results(
                            url=file_url,
                            dst_fn=parts[-1],
                            data_type="sentinel2_jp2",
                        )

                except Exception as e:
                    logger.debug(
                        f"Error parsing result {result.get('Name', 'unknown')}: {e}"
                    )
                    continue

            # Pagination
            query_url = response.get("@odata.nextLink", None)

        return self


@cli.cli_opts(
    help_text="CDSE Direct Node Fetcher (Sentinel-2 JP2 Bands)",
    collection_name="Collection (e.g., SENTINEL-2). Default: SENTINEL-2",
    product_type="Product Type (e.g., S2MSI1C, S2MSI2A). Default: S2MSI1C",
    cloud_cover="Max cloud cover percentage (0-100)",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
)
class Sentinel2_CDSE(CDSE):
    """Convenience alias for the CDSE Module defaulted to Sentinel-2."""

    def __init__(self, **kwargs):
        super().__init__(collection_name="SENTINEL-2", product_type="S2MSI1C", **kwargs)
