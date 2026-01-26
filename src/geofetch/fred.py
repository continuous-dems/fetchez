#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
geofetch.fred
~~~~~~~~~~~~~

Fetches Remote Elevation Datalist (FRED)

Handles the indexing, storage, and spatial querying of remote datasets 
that lack a public API but provide file lists (e.g., NCEI Thredds, USACE).

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import json
import logging
from typing import List, Dict, Optional, Any, Tuple, Union
from tqdm import tqdm

from . import utils
from . import spatial

try:
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)

# Directory where FRED index files are stored
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FETCH_DATA_DIR = os.path.join(THIS_DIR, 'data')

class FRED:
    """FRED (Fetches Remote Elevation Datalist) manages a local GeoJSON-based index 
    of remote files. It allows spatial queries to determine which files to download.
    """
    
    # Standard metadata schema
    SCHEMA = [
        'Name', 'ID', 'Date', 'Agency', 'MetadataLink', 'MetadataDate', 
        'DataLink', 'IndexLink', 'Link', 'DataType', 'DataSource', 
        'Resolution', 'HorizontalDatum', 'VerticalDatum', 'LastUpdate', 
        'Etcetra', 'Info'
    ]

    def __init__(self, name: str = 'FRED', local: bool = False):
        self.name = name
        self.filename = f'{name}.geojson'
        
        # Determine file path
        # If the expected file doesn't exist (in `FETCH_DATA_DIR`) we check
        # if it exists in the cwd; if not, the fetch module should create one
        # (if needed).
        # Default to local directory if not found in data dir
        if local:
            self.path = self.filename
        elif os.path.exists(os.path.join(FETCH_DATA_DIR, self.filename)):
            self.path = os.path.join(FETCH_DATA_DIR, self.filename)
        else:
            self.path = self.filename
            
        self.features = []
        self._load()

        
    def _load(self):
        """Load the GeoJSON file into memory."""
        
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.features = data.get('features', [])


                msg = (f"Loaded index {utils.colorize(self.name, utils.CYAN)} "
                       f"from {utils.str_truncate_middle(self.path)} "
                       f"({utils.colorize(str(len(self.features)), utils.BOLD)} items)")
                logger.info(msg)
                    
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Corrupt or unreadable index at {self.path}: {e}")
                self.features = []
        else:
            logger.debug(f"Index not found at {self.path}, starting empty.")
            logger.info(f"Initializing new index for {utils.colorize(self.name, utils.CYAN)}")
            self.features = []
                    
            
    def save(self):
        """Save the current features to the GeoJSON file."""
        
        data = {
            "type": "FeatureCollection",
            "name": self.name,
            "features": self.features
        }
        
        # Ensure directory exists
        out_dir = os.path.dirname(self.path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)
            
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':')) # Compact JSON
            logger.info(f"Saved {len(self.features)} items to {self.name} index.")
        except IOError as e:
            logger.error(f"Failed to save FRED index {self.path}: {e}")

            
    def add_survey(self, geom: Dict, **kwargs):
        """Add a single survey entry to the FRED database.
        
        Args:
            geom (Dict): GeoJSON geometry dictionary (e.g., {'type': 'Polygon', 'coordinates': ...})
            **kwargs: Attributes matching the schema.
        """
        
        props = kwargs.copy()
        props['LastUpdate'] = utils.this_date()
        
        # for field in self.SCHEMA:
        #     if field not in props:
        #         props[field] = None
        
        feature = {
            "type": "Feature",
            "properties": props,
            "geometry": geom
        }
        self.features.append(feature)

        
    def search(self, 
               region: Optional[Tuple[float, float, float, float]] = None, 
               where: List[str] = [], 
               layer: str = None) -> List[Dict]:
        """Search for data in the reference vector file.
        
        Args:
            region: Tuple (xmin, xmax, ymin, ymax) from spatial.parse_region
            where: List of simple SQL-style filters (e.g. "Agency = 'NOAA'")
                   (Currently supports simple equality checks for simplicity without SQL parser)
            layer: Filter by 'DataSource' field (e.g., 'ncei_thredds')
            
        Returns:
            List of dictionaries containing the properties of matching features.
        """
        
        results = []
        
        # Prepare Spatial Filter
        search_geom = None
        if region is not None and spatial.region_valid_p(region):            
            if HAS_SHAPELY:
                search_geom = spatial.region_to_shapely(region)
            else:
                search_bbox = region

        if region:
            r_str = ",".join(f"{x:.2f}" for x in region)
            logger.debug(f"Searching {self.name} in region [{r_str}]...")
                
        for feat in self.features:
            props = feat.get('properties', {})
            geom = feat.get('geometry')
            
            if layer and props.get('DataSource') != layer:
                continue
                
            # Filter by Attributes ("where")
            match = True
            for clause in where:
                if '=' in clause:
                    k, v = [x.strip().strip("'").strip('"') for x in clause.split('=')]
                    
                    val = props.get(k)
                    if str(val) != v:
                        match = False
                        break
            if not match:
                continue

            if search_geom and geom:
                if HAS_SHAPELY:
                    try:
                        feat_shape = shape(geom)
                        if not search_geom.intersects(feat_shape):
                            continue
                    except Exception:
                        continue
                else:
                    # TODO: Basic bounding box check (if Shapely missing)
                    pass 

            # If we passed all filters, add to results
            results.append(props)

        logger.info(f"FRED Search found {len(results)} items.")
        return results

    
    def _get_unique_values(self, field: str) -> List[Any]:
        """Helper to see unique values for a field (e.g. Agency)."""
        
        values = set()
        for f in self.features:
            val = f.get('properties', {}).get(field)
            if val: values.add(val)
        return list(values)
