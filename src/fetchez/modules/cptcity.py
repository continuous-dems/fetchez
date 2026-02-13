#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.cptcity
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Color Palette Tables (CPT) from CPT City.

This module downloads the package listing from CPT City to discover
available palettes and allows searching by name/category.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import zipfile
from io import BytesIO
from typing import Optional
import lxml.etree

from fetchez import core
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

CPT_PUB_URL = "http://seaviewsensing.com/pub/"
CPT_PKG_BASE_URL = "http://seaviewsensing.com/pub/cpt-city/pkg/"
PACKAGE_XML_URL = f"{CPT_PKG_BASE_URL}package.xml"


# =============================================================================
# CPT City Module
# =============================================================================
@cli.cli_opts(
    help_text="CPT City Color Palettes",
    query="Search term to filter palettes (e.g. 'bathymetry', 'topography', 'rainbow')",
)
class CPTCity(core.FetchModule):
    """Fetch various CPT files for DEM hillshades, bathymetry, and visualization."""

    def __init__(self, query: Optional[str] = None, **kwargs):
        super().__init__(name="cpt_city", **kwargs)
        self.query = query

    def run(self):
        """Run the cpt-city fetches module."""

        # Fetch Package XML to find the current zip filename
        logger.info("Fetching CPT City package info...")
        req_xml = core.Fetch(PACKAGE_XML_URL).fetch_req()

        if req_xml is None or req_xml.status_code != 200:
            logger.error("Failed to retrieve package.xml")
            return

        try:
            root = lxml.etree.fromstring(req_xml.content)
            cpt_node = root.find("cpt")

            if cpt_node is None or not cpt_node.text:
                logger.error("Could not find 'cpt' tag in package.xml")
                return

            cpt_zip_filename = cpt_node.text

        except lxml.etree.XMLSyntaxError as e:
            logger.error(f"Failed to parse XML: {e}")
            return

        # Fetch the Main Zip (Headers/Content) to list files
        # We download the zip to memory to browse it.
        # (It's usually < 20MB, so this is acceptable for discovery).
        zip_url = f"{CPT_PKG_BASE_URL}{cpt_zip_filename}"
        logger.info(f"Downloading catalog: {cpt_zip_filename}...")

        req_zip = core.Fetch(zip_url).fetch_req()
        if req_zip is None:
            return

        try:
            with zipfile.ZipFile(BytesIO(req_zip.content)) as zip_ref:
                zip_cpts = zip_ref.namelist()

            logger.info(f"Scanned {len(zip_cpts)} files in archive.")

            # Filter results
            if self.query:
                # Simple substring match
                filtered_files = [
                    x for x in zip_cpts if self.query.lower() in x.lower()
                ]
                logger.info(
                    f"Found {len(filtered_files)} palettes matching '{self.query}'"
                )
            else:
                filtered_files = zip_cpts

            # Generate download entries
            # We point to the extracted file location on the server so we don't
            # have to extract locally from the huge zip if we only want one file.
            for f in filtered_files:
                # Skip directories and non-CPT files (unless query requested them)
                if f.endswith("/"):
                    continue
                if not f.endswith(".cpt") and not self.query:
                    continue

                f_url = f"{CPT_PUB_URL}{f}"
                f_fn = f.split("/")[-1]

                self.add_entry_to_results(
                    url=f_url,
                    dst_fn=f_fn,
                    data_type="cpt",
                    agency="CPT City",
                    description=f,
                    license="Public Domain / Varies",
                )

        except Exception as e:
            logger.error(f"Error processing CPT City archive: {e}")

        return self
