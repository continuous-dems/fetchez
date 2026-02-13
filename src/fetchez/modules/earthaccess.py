#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.earthaccess
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A wrapper around the official 'earthaccess' library (NSIDC) for NASA Earth Data.
This is distinct from the 'earthdata' module (which uses raw CMR/Harmony calls).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import datetime
import urllib.parse
import posixpath
from fetchez.core import FetchModule
from fetchez import cli

logger = logging.getLogger(__name__)

@cli.cli_opts(
    help_text="NASA EarthAccess",
    short_name="Dataset Short Name (e.g. ATL03, ATL08, MUR-JPL-L4-GLOB-v4.1)",
    concept_id="Concept ID",
    version="Dataset Version (e.g. 006)",
    cloud_cover="(min/max) cloud cover"
)
class EarthAccess(FetchModule):
    """Fetch NASA Earth Data using the `earthaccess` library.
    
    This module leverages the official NSIDC `earthaccess` library to search
    and download data. 

    Prerequisites:
      pip install earthaccess
      ~/.netrc configured (earthaccess handles this interaction)

    Args:
        short_name (str): The dataset Short Name (e.g. 'ATL03').
        concept_id (str): Optional Concept ID override.
        version (str): Dataset version (optional).
        cloud_cover (tuple): (min, max) cloud cover.
    """

    def __init__(self, short_name=None, concept_id=None, version=None, **kwargs):
        super().__init__(**kwargs)
        self.short_name = short_name
        self.concept_id = concept_id
        self.version = version
        self.extra_params = kwargs

        self.tags = ['nasa', 'earthdata', 'earthaccess', 'cmr']
        if short_name:
            self.tags.append(short_name.lower())

    def run(self):
        try:
            import earthaccess
        except ImportError:
            logger.error("Module 'earthaccess' requires the library. Run: pip install earthaccess")
            return

        try:
            auth = earthaccess.login(strategy="netrc")
            if not auth.authenticated:
                logger.warning("EarthAccess: Not authenticated. Public data only, or prompt incoming.")
                earthaccess.login(strategy="interactive") 
        except Exception as exception:
            logger.warning(f"EarthAccess Login Warning: {exception}")

        bbox = None
        if self.region:
            w, e, s, n = self.region
            bbox = (w, s, e, n)

        temporal = None
        if self.min_year or self.max_year:
            start = f"{self.min_year}-01-01" if self.min_year else "1900-01-01"
            end = f"{self.max_year}-12-31" if self.max_year else datetime.datetime.now().strftime("%Y-%m-%d")
            temporal = (start, end)

        logger.info(f"Searching CMR (via earthaccess) for {self.short_name or self.concept_id}...")

        # this might be the wrong way to go about this. `search_data` crashes
        # if we don't include the concept id though...revisit this at some point.
        if self.concept_id is None:
            datasets = earthaccess.search_datasets(short_name=self.short_name)
            self.concept_id = datasets[0]["meta"]["concept-id"]

        try:
            results = earthaccess.search_data(
                short_name=self.short_name,
                concept_id=self.concept_id,
                version=self.version,
                bounding_box=bbox,
                temporal=temporal,
                count=-1, # Get all matching
                #**self.extra_params
            )
        except Exception as e:
            logger.error(f"CMR Search failed: {e}")
            return

        logger.info(f"Found {len(results)} granules.")

        for granule in results:
            links = granule.data_links(access='external')
            
            if not links:
                continue

            data_url = None
            for link in links:
                lower_link = link.lower()
                if not lower_link.endswith(('.xml', '.jpg', '.png', '.iso', '.pdf')):
                    data_url = link
                    break
            
            if not data_url:
                data_url = links[0]

            path = urllib.parse.urlparse(data_url).path
            dst_fn = posixpath.basename(path)
            
            self.results.append({
                "url": data_url,
                "dst_fn": dst_fn,
                "data_type": "cmr_granule",
                "earthaccess_granule": granule 
            })
