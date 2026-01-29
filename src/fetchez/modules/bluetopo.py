#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.bluetopo
~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA BlueTopo bathymetric data.

BlueTopo is a compilation of the nation's best available bathymetric data,
created as part of the Office of Coast Survey's National Bathymetric Source project.
Data is delivered as multi-band GeoTIFFs (Elevation, Uncertainty, Source).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from typing import Optional

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.client import Config
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

try:
    from osgeo import ogr
except ImportError:
    ogr = None

from fetchez import core
from fetchez import utils
from fetchez import cli

logger = logging.getLogger(__name__)

BLUETOPO_BUCKET = 'noaa-ocs-nationalbathymetry-pds'
BLUETOPO_PREFIX = 'BlueTopo'

# =============================================================================
# BlueTopo Module
# =============================================================================
@cli.cli_opts(
    help_text='NOAA BlueTopo Bathymetry (S3)',
    want_interpolation='Accept interpolated data (Downstream processing flag)',
    unc_weights='Use uncertainty weights (Downstream processing flag)',
    keep_index='Keep the downloaded tile index file after running'
)
class BlueTopo(core.FetchModule):
    """
    Fetch NOAA BlueTopo Data.
    
    This module downloads the BlueTopo Tile Scheme (GeoPackage) from the 
    public S3 bucket, performs a spatial query to find intersecting tiles, 
    and generates download links for the corresponding TIFFs.
    
    Requires: 'boto3' and 'gdal/ogr' libraries.
    """
    
    def __init__(self, 
                 want_interpolation: bool = False,
                 unc_weights: bool = False,
                 keep_index: bool = False,
                 **kwargs):
        super().__init__(name='bluetopo', **kwargs)
        self.want_interpolation = want_interpolation
        self.unc_weights = unc_weights
        self.keep_index = keep_index
        
        self._bluetopo_index_url = None
        self._bluetopo_index_fn = None

        
    def _get_s3_client(self):
        """Return an anonymous S3 client."""
        
        return boto3.client('s3', config=Config(signature_version=UNSIGNED))

    
    def _get_index_url(self, s3_client) -> Optional[str]:
        """Dynamically find the Tile Scheme index file URL from S3."""
        
        try:
            r = s3_client.list_objects(
                Bucket=BLUETOPO_BUCKET, 
                Prefix=f'{BLUETOPO_PREFIX}/_BlueTopo_Tile_Scheme'
            )
            
            if 'Contents' in r and len(r['Contents']) > 0:
                key = r['Contents'][0]['Key']
                return f'https://{BLUETOPO_BUCKET}.s3.amazonaws.com/{key}'
        except Exception as e:
            logger.error(f'Error finding BlueTopo index on S3: {e}')
        
        return None

    
    def run(self):
        """Run the BlueTopo fetch module."""

        if not HAS_BOTO:
            logger.error('This module requires "boto3". Please install it to proceed.')
            return
        
        if self.region is None:
            return []
            
        if not ogr:
            logger.error('BlueTopo requires "osgeo.ogr" (GDAL) to parse the tile index.')
            return self

        s3 = self._get_s3_client()
        
        if self._bluetopo_index_url is None:
            logger.info('Locating BlueTopo Tile Scheme on S3...')
            self._bluetopo_index_url = self._get_index_url(s3)
            
        if not self._bluetopo_index_url:
            logger.error('Could not locate BlueTopo tile index.')
            return self

        self._bluetopo_index_fn = os.path.basename(self._bluetopo_index_url)
        
        try:
            if not os.path.exists(self._bluetopo_index_fn):
                logger.info(f'Downloading index: {self._bluetopo_index_fn}...')
                status = core.Fetch(
                    self._bluetopo_index_url
                ).fetch_file(self._bluetopo_index_fn)
                
                if status != 0:
                    raise IOError('Failed to download BlueTopo index.')

            logger.info("Querying tile index...")
            v_ds = ogr.Open(self._bluetopo_index_fn)
            if v_ds is None:
                raise IOError('Failed to open BlueTopo index (GeoPackage).')

            layer = v_ds.GetLayer()
            
            w, e, s, n = self.region
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(w, s)
            ring.AddPoint(w, n)
            ring.AddPoint(e, n)
            ring.AddPoint(e, s)
            ring.AddPoint(w, s)
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)
            
            layer.SetSpatialFilter(poly)
            
            feature_count = layer.GetFeatureCount()
            if feature_count == 0:
                logger.info('No BlueTopo tiles found in this region.')
                return self
                
            logger.info(f'Found {feature_count} intersecting tiles.')

            for feature in layer:
                tile_name = feature.GetField('tile')
                
                try:
                    r = s3.list_objects(
                        Bucket=BLUETOPO_BUCKET,
                        Prefix=f'{BLUETOPO_PREFIX}/{tile_name}'
                    )
                    
                    if 'Contents' in r:
                        for obj in r['Contents']:
                            key = obj['Key']
                            if key.endswith('.tiff'):
                                data_link = f'https://{BLUETOPO_BUCKET}.s3.amazonaws.com/{key}'
                                self.add_entry_to_results(
                                    url=data_link,
                                    dst_fn=os.path.basename(key),
                                    data_type='bluetopo_tiff',
                                    agency='NOAA OCS',
                                    title=tile_name,
                                    license='Public Domain'
                                )
                except Exception as e:
                    logger.warning(f'Failed to resolve file for tile {tile_name}: {e}')

            v_ds = None

        except Exception as e:
            logger.error(f'BlueTopo Run Error: {e}')
            
        finally:
            if not self.keep_index and self._bluetopo_index_fn:
                if os.path.exists(self._bluetopo_index_fn):
                    try:
                        os.remove(self._bluetopo_index_fn)
                    except OSError:
                        pass
            
        return self
