#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.charts
~~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA Nautical Charts (ENC) using official XML Catalogs.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import copy

from fetchez import core
from fetchez import fred
from fetchez import cli

logger = logging.getLogger(__name__)

ENC_CATALOG_URL = "https://charts.noaa.gov/ENCs/ENCProdCat_19115.xml"
# RNC_CATALOG_URL = 'https://charts.noaa.gov/RNCs/RNCProdCat_19115.xml'


# =============================================================================
# NOAA Charts Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA Nautical Charts (ENC)",
    update="Force update of the local catalog index (FRED)",
)
class NOAACharts(core.FetchModule):
    """Fetch NOAA Nautical Charts.

    This module downloads the official NOAA ISO 19115 XML catalogs for
    ENC (Electronic Nautical Charts).
    indexes them locally using FRED, and allows spatial querying.
    """

    def __init__(self, update: bool = False, **kwargs):
        super().__init__(name="charts", **kwargs)
        self.force_update = update

        # Initialize FRED (Local Index)
        self.fred = fred.FRED(name="noaa_charts")

        # Check if we need to populate/update the index
        if self.force_update or len(self.fred.features) == 0:
            self.update_index()

    def update_index(self):
        """Download XML catalogs and update the local FRED index."""
        logger.info("Updating NOAA Charts Catalog (this may take a minute)...")

        # Clear existing entries
        self.fred.features = []

        catalogs_to_fetch = []
        # if self.chart_type in ['ENC', 'ALL']:
        catalogs_to_fetch.append(("ENC", ENC_CATALOG_URL))
        # if self.chart_type in ['RNC', 'ALL']:
        #    catalogs_to_fetch.append(('RNC', RNC_CATALOG_URL))

        for c_type, url in catalogs_to_fetch:
            logger.info(f"Fetching {c_type} Catalog...")

            # Use core.iso_xml to fetch and parse the main catalog
            catalog_xml = core.iso_xml(url, timeout=60, read_timeout=120)

            if catalog_xml.xml_doc is None:
                logger.error(f"Failed to load {c_type} XML Catalog.")
                continue

            # NOAA Catalogs are DS_Series.
            # We look for all 'has' tags (ignoring namespaces using {*})
            # This finds the wrappers around the individual MD_Metadata entries.
            chart_nodes = catalog_xml.xml_doc.findall(".//{*}has")

            logger.info(f"Parsing {len(chart_nodes)} {c_type} entries...")

            count = 0
            for node in chart_nodes:
                # We need to act on the *child* of the 'has' tag,
                # or create a new iso_xml instance scoped to this node.
                # A quick way is to copy the helper and swap the root doc.

                chart_helper = copy.copy(catalog_xml)
                chart_helper.xml_doc = node

                # Extract Info
                title = chart_helper.title()
                link = chart_helper.linkages()
                geom = chart_helper.polygon(geom=True)
                desc = chart_helper.abstract()
                date = chart_helper.date()

                # Use title as ID if no explicit ID found, but title is usually the Chart ID (e.g. US1AK90M)
                chart_id = title if title else f"{c_type}_{count}"

                if geom and link:
                    self.fred.add_survey(
                        geom=geom,
                        Name=chart_id,
                        ID=chart_id,
                        Description=desc,
                        Agency="NOAA",
                        DataLink=link,
                        DataType=c_type,
                        Date=date,
                        DataSource="charts",
                    )
                    count += 1

            logger.info(f"Indexed {count} {c_type} charts.")

        self.fred.save()

    def run(self):
        """Run the Charts fetcher."""

        if self.region is None:
            return []

        # Filter by chart type
        where_clause = []
        # if self.chart_type != 'ALL':
        where_clause.append("DataType = 'ENC'")

        # Query FRED
        results = self.fred.search(region=self.region, where=where_clause)

        if not results:
            logger.info("No charts found in this region.")
            return

        for item in results:
            url = item.get("DataLink")
            name = item.get("Name")
            c_type = item.get("DataType")
            desc = item.get("Description")

            if url:
                self.add_entry_to_results(
                    url=url,
                    dst_fn=os.path.basename(url),
                    data_type=c_type,
                    agency="NOAA",
                    title=name,
                    description=desc,
                    license="Public Domain",
                )

        return self
