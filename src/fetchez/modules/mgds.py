#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.mgds
~~~~~~~~~~~~~~~~~~~~

Fetch marine geophysical data from the Marine Geoscience Data System (MGDS).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from fetchez import core
from fetchez import cli

try:
    from lxml import etree
except ImportError:
    import xml.etree.ElementTree as etree

logger = logging.getLogger(__name__)

MGDS_FILE_URL = "https://www.marine-geo.org/services/FileServer"
MGDS_NAMESPACE = "https://www.marine-geo.org/services/xml/mgdsDataService"


# =============================================================================
# MGDS Module
# =============================================================================
@cli.cli_opts(
    help_text="Marine Geoscience Data System (MGDS)",
    datatype="Data type (e.g., 'Bathymetry', 'Bathymetry:Swath'). Default: 'Bathymetry'",
)
class MGDS(core.FetchModule):
    """
    Fetch marine data from MGDS.

    MGDS is a trusted data repository that provides free public access
    to a curated collection of marine geophysical data products.

    Common Data Types:
      - Bathymetry
      - Bathymetry:Swath
      - Bathymetry:Singlebeam
      - Bathymetry:Phase
      - Bathymetry:BPI

    References:
      - https://www.marine-geo.org
    """

    def __init__(self, datatype: str = "Bathymetry", **kwargs):
        super().__init__(name="mgds", **kwargs)
        self.datatype = datatype.replace(",", ":")

    def run(self):
        """Run the MGDS fetching logic."""

        if self.region is None:
            return []

        w, e, s, n = self.region

        search_params = {
            "north": n,
            "west": w,
            "south": s,
            "east": e,
            "format": "summary",
            "data_type": self.datatype,
        }

        logger.info(f"Searching MGDS for '{self.datatype}'...")
        req = core.Fetch(MGDS_FILE_URL).fetch_req(params=search_params, timeout=20)

        if not req or req.status_code != 200:
            logger.error("Failed to query MGDS FileServer.")
            return self

        try:
            tree = etree.fromstring(req.content)

            ns_tag = f"{{{MGDS_NAMESPACE}}}file"
            results = tree.findall(f".//{ns_tag}")

            logger.info(f"Found {len(results)} potential files.")

            for res in results:
                name = res.attrib.get("name")
                link = res.attrib.get("download")

                if name and link:
                    self.add_entry_to_results(
                        url=link,
                        dst_fn=name,
                        data_type="mgds_file",
                        agency="MGDS",
                        title=name,
                    )

        except Exception as e:
            logger.error(f"Error parsing MGDS XML: {e}")

        return self
