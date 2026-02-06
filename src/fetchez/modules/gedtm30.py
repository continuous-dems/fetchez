#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.gedtm30
~~~~~~~~~~~~~~~~~~~~~~~

Fetch Global 1-Arc-Second Digital Terrain Model (GEDTM30) data 
from OpenLandMap.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import csv
import logging
from io import StringIO
from fetchez import core
from fetchez import cli

logger = logging.getLogger(__name__)

# Direct link to the metadata CSV listing all available COGs
# moved to codeberg.
GEDTM30_COG_LIST_URL = 'https://codeberg.org/openlandmap/GEDTM30/src/branch/main/metadata/cog_list.csv'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'referer': 'https://codeberg.org/openlandmap/GEDTM30'
}

# codeberg won't let us get this directly; so just copy/paste here for use.
CONTENT = """
name,doi,scale,data_type,no_data,measurement unit,url,,,,,,
Ensemble Digital Terrain Model v1.1,https://zenodo.org/records/15689805,10,Int32,-2147483647,meter,https://s3.opengeohub.org/global/edtm/gedtm_rf_m_30m_s_20060101_20151231_go_epsg.4326.3855_v20250611.tif,,,,,,
Standard Deviation EDTM v1.1,https://zenodo.org/records/15689805,100,UInt16,65535,meter,https://s3.opengeohub.org/global/edtm/gedtm_rf_std_30m_s_20060101_20151231_go_epsg.4326.3855_v20250611.tif,,,,,,
Global-to-local mask v1.1,https://zenodo.org/records/15689805,1,Byte,255,,https://s3.opengeohub.org/global/edtm/gedtm_mask_c_120m_s_20060101_20151231_go_epsg.4326.3855_v20250611.tif,,,,,,
Ensemble Digital Terrain Model v1.0,https://zenodo.org/records/14900181,10,Int32,-2147483647,meter,https://s3.opengeohub.org/global/edtm/legendtm_rf_30m_m_s_20000101_20231231_go_epsg.4326_v20250130.tif,,,,,,
Standard Deviation EDTM v1.0,https://zenodo.org/records/14900181,100,UInt16,65535,meter,https://s3.opengeohub.org/global/edtm/gendtm_rf_30m_std_s_20000101_20231231_go_epsg.4326_v20250209.tif,,,,,,
Difference from Mean Elevation,https://zenodo.org/records/14919451,100,Int16,32767,,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/dfme_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Geomorphons,https://zenodo.org/records/14920357,1,Byte,255,,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/geomorphon_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Hillshade,https://zenodo.org/records/14920359,1,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/hillshade_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
LS Factor,https://zenodo.org/records/14920361,1000,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ls.factor_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Maximal Curvature,https://zenodo.org/records/14920363,1000,Int16,32767,m-1,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/maxic_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Minimal Curvature,https://zenodo.org/records/14920365,1000,Int16,32767,m-1,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/minic_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Negative Openness,https://zenodo.org/records/14920369,100,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/neg.openness_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Positive Openness,https://zenodo.org/records/14920371,100,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pos.openness_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Profile Curvature,https://zenodo.org/records/14920373,1000,Int16,32767,m-1,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/pro.curv_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Ring Curvature,https://zenodo.org/records/14920375,10000,Int16,32767,m-2,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ring.curv_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Shape Index,https://zenodo.org/records/14920377,1000,Int16,32767,,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/shpindx_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Slope in Degree,https://zenodo.org/records/14920379,100,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/slope.in.degree_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Specific Catchment Area,https://zenodo.org/records/14920381,1000,UInt16,65535,,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/spec.catch_edtm_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Spherical Standard Deviation of the Normals,https://zenodo.org/records/14920383,100,Int16,32767,,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/ssdon_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Tangential Curvature,https://zenodo.org/records/14920385,1000,Int16,32767,m-1,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/tan.curv_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
Topographic Wetness Index,https://zenodo.org/records/14920387,100,Int16,32767,,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_30m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_60m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_120m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_240m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_480m_s_20000101_20221231_go_epsg.4326_v20241230.tif,https://s3.opengeohub.org/global/dtm/v3/twi_edtm_m_960m_s_20000101_20221231_go_epsg.4326_v20241230.tif
"""

# =============================================================================
# GEDTM30 Module
# =============================================================================
@cli.cli_opts(
    help_text="OpenLandMap GEDTM30 (Global 30m DTM)",
    product="Product Name (e.g., 'Ensemble Digital Terrain Model', 'dtm_downscaled')"
)
class GEDTM30(core.FetchModule):
    """Fetch Global 1-Arc-Second (30m) Digital Terrain Models.
    
    This module queries the OpenLandMap GEDTM30 repository to find 
    Cloud Optimized GeoTIFFs (COGs) matching the requested product name.
    
    Common Products:
      - 'Ensemble Digital Terrain Model' (Default)
      - 'dtm_downscaled'
      - 'dtm_bareearth'
    
    References:
      - https://codeberg.org/openlandmap/GEDTM30
    """
    
    def __init__(self, product: str = 'Ensemble Digital Terrain Model', **kwargs):
        super().__init__(name='gedtm30', **kwargs)
        self.product = product
        self.headers = HEADERS

    def run(self):
        """Run the GEDTM30 fetching logic."""
        
        logger.info("Fetching GEDTM30 file list...")
        req = core.Fetch(GEDTM30_COG_LIST_URL).fetch_req()
        
        if not req or req.status_code != 200:
            logger.error("Failed to retrieve GEDTM30 metadata list.")
            return self

        try:
            f = StringIO(CONTENT)
            #f = StringIO(req.text)
            reader = csv.reader(f)
            
            header = next(reader, None)
            
            matches = 0
            for row in reader:
                if not row: continue
                
                # Column 0 is the Product Name
                # Column -1 is the Download URL
                prod_name = row[0]
                url = row[6]
                
                if self.product.lower() in prod_name.lower():
                    print(row)
                    fname = os.path.basename(url)
                    
                    self.add_entry_to_results(
                        url=url,
                        dst_fn=fname,
                        data_type='geotiff',
                        agency='OpenLandMap',
                        title=prod_name
                    )
                    matches += 1
            
            if matches == 0:
                logger.warning(f"No products found matching '{self.product}'.")
            else:
                logger.info(f"Found {matches} files for '{self.product}'.")
                print(matches)

        except Exception as e:
            logger.error(f"Error parsing GEDTM30 CSV: {e}")

        return self
