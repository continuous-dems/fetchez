#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.spatial
~~~~~~~~~~~~~~~~

Lightweight spatial utilities for parsing region strings and files into 
standard bounding boxes. Based on cudem.regions

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import json
import math
import logging
from typing import Union, List, Tuple, Optional

try:
    from shapely.geometry import shape, box, mapping
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

from . import utils 

logger = logging.getLogger(__name__)

def region_help_msg():
    return """Region Formats:
  xmin/xmax/ymin/ymax      : Bounding box
  loc:City,State           : Geocode place name
  file.geojson             : Bounding box of vector file
    """


def region_from_string(r_str: str) -> Optional[Tuple[float, float, float, float]]:
    """Parse a standard GMT-style region string (e.g. -R-105/-104/39/40)."""
    
    if not r_str: return None
        
    if r_str.startswith('-R'):
        r_str = r_str[2:]
    elif r_str.startswith('--region='):
        r_str = r_str.split('=')[1]
        
    parts = r_str.split('/')
    if len(parts) < 4: return None
        
    try:
        return tuple(float(x) for x in parts[:4])
    except ValueError:
        return None

    
def region_from_list(r_list: List[float]) -> Optional[Tuple[float, float, float, float]]:
    """Convert a list of 4 numbers to a bounding box tuple.

    The order should be [w, e, s, n]
    """
    
    if len(r_list) < 4: return None
    try:
        return (float(r_list[0]), float(r_list[1]), float(r_list[2]), float(r_list[3]))
    except (ValueError, TypeError):
        return None

    
def region_from_geojson(fn: str) -> Optional[Tuple[float, float, float, float]]:
    """Parse the bounding box of a GeoJSON file."""
    
    if not os.path.exists(fn): return None
    regions = []
    try:
        with open(fn, 'r') as f:
            data = json.load(f)
        
        features = data.get('features', [data])
        
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        valid = False
        
        for feat in features:
            geom = feat.get('geometry', feat)
            if not geom: continue
            
            if HAS_SHAPELY:
                b = shape(geom).bounds # (minx, miny, maxx, maxy)
                min_x = min(min_x, b[0])
                min_y = min(min_y, b[1])
                max_x = max(max_x, b[2])
                max_y = max(max_y, b[3])
                valid = True
            else:
                pass

            if valid:
                regions.append((min_x, max_x, min_y, max_y))
        if regions:
            return regions
    except Exception as e:
        logger.warning(f'Failed to parse GeoJSON {fn}: {e}')
        
    return None


def region_from_place(query: str, centered: bool=True) -> Optional[Tuple[float, float, float, float]]:
    """Resolve 'loc:PlaceName' to a bounding box."""
    
    from .modules.nominatim import Nominatim
    
    clean_q = query.split(':', 1)[1] if ':' in query else query
    
    nom = Nominatim(query=clean_q)
    nom.run()
    
    if nom.results:
        res = nom.results[0]
        x = res.get('x')
        y = res.get('y')

        if centered:
            if x is not None and y is not None:
                # region is centered on place
                x_min = x - .125
                x_max = x + .125
                y_min = y - .125
                y_max = y + .125
                return (x_min, x_max, y_min, y_max)

        else:
            if x is not None and y is not None:
                # Snap to 0.25 degree grid
                x_min = math.floor(x * 4) / 4
                x_max = math.ceil(x * 4) / 4
                y_min = math.floor(y * 4) / 4
                y_max = math.ceil(y * 4) / 4
                return (x_min, x_max, y_min, y_max)
            
    return None


def _coordinate_list_p(lst: List) -> bool:
    """Check if a list looks like [x, x, y, y]."""
    
    if len(lst) != 4: 
        return False
    try:
        # Check if all items can be cast to float
        [float(x) for x in lst]
        return True
    except (ValueError, TypeError):
        return False

_is_coordinate_list = _coordinate_list_p


def parse_single_string(s: str) -> Optional[Tuple[float, float, float, float]]:
    """Parse a single string (presumably a representation of a region) input."""
    
    s_lower = s.lower()
    
    # File Paths
    if s_lower.endswith('.json') or s_lower.endswith('.geojson'):
        return region_from_geojson(s)
        
    # Place Names
    if s_lower.startswith(('loc:', 'place:')):
        return region_from_place(s)
        
    # Standard String (-R...)
    return region_from_string(s)


def parse_region(input_r: Union[str, List]) -> List[Tuple[float, float, float, float]]:
    """Main function to parse any region input into a list of (xmin, xmax, ymin, ymax) tuples.
    
    Returns:
        List[Tuple]: A list of bounding boxes. Returns empty list if parsing fails.
    """
    
    regions = []
    # Single String
    if isinstance(input_r, str):
        r = parse_single_string(input_r)
        if r:
            if isinstance(r, tuple):
                regions.append(r)
            elif isinstance(r, list):
                regions.extend(r)
        return regions

    # Lists (could be coords OR list of identifier strings)
    if isinstance(input_r, (list, tuple)):
        
        # Check if it is a single Coordinate List [x, x, y, y]
        if _coordinate_list_p(input_r):
            r = region_from_list(input_r)
            if r: regions.append(r)
        
        # Otherwise, treat as a list of independent region strings
        else:
            for item in input_r:
                if isinstance(item, str):
                    r = parse_single_string(item)
                    if r:
                        if isinstance(r, tuple):
                            regions.append(r)
                        elif isinstance(r, list):
                            regions.extend(r)
                elif isinstance(item, (list, tuple)) and _coordinate_list_p(item):
                    r = region_from_list(item)
                    if r: regions.append(r)

    if not regions:
        logger.warning(f'Failed to parse region {input_r}')
    return regions


def region_valid_p(region: Optional[Tuple[float, float, float, float]], check_xy: bool = True) -> bool:
    """Check if a region tuple is valid.
    
    A region is considered valid if:
    1. It is a list or tuple of exactly 4 numbers.
    2. xmin < xmax
    3. ymin < ymax
    
    Args:
        region: The region tuple (xmin, xmax, ymin, ymax).
        check_xy: If True, enforces strict inequality (min < max). 
                  If False, allows points/lines (min <= max).
    
    Returns:
        bool: True if valid, False otherwise.
    """
    
    if region is None:
        return False
        
    if not isinstance(region, (list, tuple)) or len(region) < 4:
        return False
        
    try:
        xmin, xmax, ymin, ymax = map(float, region[:4])
    except (ValueError, TypeError):
        return False

    if check_xy:
        if xmin >= xmax:
            return False
        if ymin >= ymax:
            return False
    else:
        if xmin > xmax:
            return False
        if ymin > ymax:
            return False
            
    return True

region_is_valid = region_valid_p


def buffer_region(bbox: Tuple, pct: float = 5) -> Tuple[float, float, float, float]:
    """Apply a percentage buffer to a bounding box."""
    
    if not bbox: return None
    
    xmin, xmax, ymin, ymax = bbox
    x_span = xmax - xmin
    y_span = ymax - ymin
    
    buf_x = x_span * (pct / 100.0)
    buf_y = y_span * (pct / 100.0)
    avg_buf = (buf_x + buf_y) / 2.0
    
    return (xmin - avg_buf, xmax + avg_buf, ymin - avg_buf, ymax + avg_buf)


def region_center(region: Tuple[float, float, float, float]):
    """Calculate the center of a region."""

    w, e, s, n = region
    center_lon = (w + e) / 2
    center_lat = (s + n) / 2

    return center_lon, center_lat


def region_to_shapely(region: Tuple[float, float, float, float]):
    """Convert a fetchez region (xmin, xmax, ymin, ymax) to a shapely box.
    
    fetchez regions are like GMT: (west, east, south, north) while
    shapely regions are not: (minx, miny, maxx, maxy)
    """
    
    if not region or not HAS_SHAPELY:
        return None
        
    west, east, south, north = region
    return box(west, south, east, north)


def region_to_wkt(region: Tuple[float, float, float, float]):
    """Convert a fetchez region (xmin, xmax, ymin, ymax) to WKT (via shapely)"""

    polygon = region_to_shapely(region)
    return polygon.wkt


def region_to_bbox(region: Tuple[float, float, float, float]):
    """Convert a fetchez region to a `bbox`"""

    w, e, s, n = region
    return (w, s, e, n)


def region_to_geojson_geom(region: Tuple[float, float, float, float]):
    w, e, s, n = region
    # geom = {
    #     "type": "Polygon",
    #     "coordinates": [[
    #         [w, s], [e, s], [e, n], [w, n], [w, s]
    #     ]]
    # }

    return {
        'type': 'Polygon',
        'coordinates': [[
            [w, s],
            [w, n],
            [e, n],
            [e, s],
            [w, s]
        ]]
    }



def chunk_region(region: Tuple[float, float, float, float], chunk_size: float = 1.0) -> List[Tuple[float, float, float, float]]:
    """Split a region into smaller sub-regions of a specified size.
    
    Args:
        region: Tuple (west, east, south, north)
        chunk_size: Size of the square chunks in degrees (or region units).
        
    Returns:
        List of (w, e, s, n) tuples.
    """
    
    w, e, s, n = region
    
    chunks = []
    
    cur_w = w
    while cur_w < e:
        next_w = cur_w + chunk_size
        if next_w > e:
            next_w = e
            
        cur_s = s
        while cur_s < n:
            next_s = cur_s + chunk_size
            if next_s > n:
                next_s = n
                
            if (next_w - cur_w > 1e-9) and (next_s - cur_s > 1e-9):
                chunks.append((cur_w, next_w, cur_s, next_s))
                
            cur_s = next_s
            
        cur_w = next_w
        
    return chunks
