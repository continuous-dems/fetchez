#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.spatial
~~~~~~~~~~~~~~~~

Lightweight spatial utilities for parsing region strings and files into
standard bounding boxes. Adaptded from CUDEM.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import json
import math
import logging
from typing import Union, List, Tuple, Optional, Any

try:
    from shapely.geometry import shape, box, mapping
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)

def region_help_msg():
    return """Region Formats:
  xmin/xmax/ymin/ymax      : Bounding box
  loc:City,State           : Geocode place name
  file.geojson             : Bounding box of vector file
    """

# =============================================================================
# The Region Class
# =============================================================================
class Region:
    """A geospatial bounding box object.

    Behaves like a tuple (xmin, xmax, ymin, ymax) for backward compatibility,
    but provides methods for manipulation and format conversion.
    """

    def __init__(self, w=None, e=None, s=None, n=None, srs=None):
        self.xmin = float(w) if w is not None else None
        self.xmax = float(e) if e is not None else None
        self.ymin = float(s) if s is not None else None
        self.ymax = float(n) if n is not None else None
        self.srs = srs  # Placeholder for EPSG/WKT string (used by transformez/dlim)


    # --- Tuple Compatibility  ---
    def __iter__(self):
        """Unpacks as: w, e, s, n = region"""

        yield self.xmin
        yield self.xmax
        yield self.ymin
        yield self.ymax


    def __getitem__(self, index):
        """Allows indexing: region[0]"""

        return [self.xmin, self.xmax, self.ymin, self.ymax][index]


    def __len__(self):
        """Allows len(region), always returns 4."""

        return 4


    def __repr__(self):
        srs_str = f", srs='{self.srs}'" if self.srs else ""
        return f"Region({self.xmin}, {self.xmax}, {self.ymin}, {self.ymax}{srs_str})"


    def __eq__(self, other):
        if isinstance(other, (list, tuple)) and len(other) == 4:
            return list(self) == list(other)
        if isinstance(other, Region):
            return (self.xmin == other.xmin and self.xmax == other.xmax and
                    self.ymin == other.ymin and self.ymax == other.ymax)
        return False


    # --- Properties ---
    @property
    def w(self): return self.xmin
    @property
    def e(self): return self.xmax
    @property
    def s(self): return self.ymin
    @property
    def n(self): return self.ymax

    @property
    def width(self): return abs(self.xmax - self.xmin) if self.valid_p() else 0
    @property
    def height(self): return abs(self.ymax - self.ymin) if self.valid_p() else 0


    # --- Validation ---
    def valid_p(self, check_xy: bool = True) -> bool:
        """Check if region is valid."""

        if None in [self.xmin, self.xmax, self.ymin, self.ymax]:
            return False

        try:
            if check_xy:
                if self.xmin >= self.xmax: return False
                if self.ymin >= self.ymax: return False
            else:
                if self.xmin > self.xmax: return False
                if self.ymin > self.ymax: return False
        except (ValueError, TypeError):
            return False
        return True


    # --- Manipulation ---
    def copy(self):
        return Region(self.xmin, self.xmax, self.ymin, self.ymax, srs=self.srs)


    def buffer(self, pct: float = 5, x_bv: float | None = None, y_bv: float | None = None):
        """Buffer the region in place."""

        if not self.valid_p(check_xy=False): return self

        if x_bv is None and y_bv is None:
            x_span = self.xmax - self.xmin
            y_span = self.ymax - self.ymin
            x_bv = x_span * (pct / 100.0)
            y_bv = y_span * (pct / 100.0)
            # Average buffer if not specified separately
            avg_buf = (x_bv + y_bv) / 2.0
            x_bv = avg_buf
            y_bv = avg_buf

        x_bv = x_bv if x_bv else 0
        y_bv = y_bv if y_bv else 0

        self.xmin -= x_bv
        self.xmax += x_bv
        self.ymin -= y_bv
        self.ymax += y_bv
        return self


    def center(self):
        """Return center (x, y)."""

        if not self.valid_p(check_xy=False): return (None, None)
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)


    def chunk(self, chunk_size: float = 1.0) -> List['Region']:
        """Split into smaller sub-regions."""

        if not self.valid_p(): return []

        chunks = []
        cur_w = self.xmin
        while cur_w < self.xmax:
            next_w = cur_w + chunk_size
            if next_w > self.xmax: next_w = self.xmax

            cur_s = self.ymin
            while cur_s < self.ymax:
                next_s = cur_s + chunk_size
                if next_s > self.ymax: next_s = self.ymax

                # Check for tiny slivers
                if (next_w - cur_w > 1e-9) and (next_s - cur_s > 1e-9):
                    chunks.append(Region(cur_w, next_w, cur_s, next_s, srs=self.srs))

                cur_s = next_s
            cur_w = next_w
        return chunks


    # --- Export Formats ---
    def to_bbox(self):
        """Export as standard (w, s, e, n) bbox used by many GIS tools."""

        return (self.xmin, self.ymin, self.xmax, self.ymax)


    def to_list(self):
        """Export as [w, e, s, n] list."""

        return [self.xmin, self.xmax, self.ymin, self.ymax]


    def format(self, style='gmt'):
        """String representation."""

        if style == 'gmt':
            return f"-R{self.xmin}/{self.xmax}/{self.ymin}/{self.ymax}"
        elif style == 'bbox':
            return f"{self.xmin},{self.ymin},{self.xmax},{self.ymax}"
        elif style == 'fn':
            # filename safe string
            return f"w{self.xmin}_e{self.xmax}_s{self.ymin}_n{self.ymax}".replace('.', 'p').replace('-', 'n')
        return str(self)


    def to_shapely(self):
        if not HAS_SHAPELY: return None
        return box(self.xmin, self.ymin, self.xmax, self.ymax)


    def to_wkt(self):
        if HAS_SHAPELY:
            return self.to_shapely().wkt
        else:
            # Simple fallback WKT
            return (f"POLYGON (({self.xmin} {self.ymin}, {self.xmin} {self.ymax}, "
                    f"{self.xmax} {self.ymax}, {self.xmax} {self.ymin}, "
                    f"{self.xmin} {self.ymin}))")


    def to_geojson_geometry(self):
        return {
            'type': 'Polygon',
            'coordinates': [[
                [self.xmin, self.ymin],
                [self.xmin, self.ymax],
                [self.xmax, self.ymax],
                [self.xmax, self.ymin],
                [self.xmin, self.ymin]
            ]]
        }


    # --- Constructors ---
    @classmethod
    def from_list(cls, r_list):
        if len(r_list) < 4: return None
        return cls(r_list[0], r_list[1], r_list[2], r_list[3])


    @classmethod
    def from_string(cls, r_str):
        if not r_str: return None
        if r_str.startswith('-R'): r_str = r_str[2:]
        elif r_str.startswith('--region='): r_str = r_str.split('=')[1]

        parts = r_str.split('/')
        if len(parts) < 4: return None
        try:
            return cls(*[float(x) for x in parts[:4]])
        except ValueError:
            return None


# =============================================================================
# Helper / Parser Functions
# =============================================================================
def region_from_geojson(fn: str) -> Optional[List[Region]]:
    """Parse the bounding box(es) of a GeoJSON file."""

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
                min_x, min_y = min(min_x, b[0]), min(min_y, b[1])
                max_x, max_y = max(max_x, b[2]), max(max_y, b[3])
                valid = True

            # Simple fallback for Polygon geometry if no shapely
            elif geom.get('type') == 'Polygon':
                coords = geom.get('coordinates', [])[0]
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                min_x, min_y = min(min_x, min(xs)), min(min_y, min(ys))
                max_x, max_y = max(max_x, max(xs)), max(max_y, max(ys))
                valid = True

        if valid:
            # We return a list containing the union bbox for now
            regions.append(Region(min_x, max_x, min_y, max_y))
            return regions
    except Exception as e:
        logger.warning(f'Failed to parse GeoJSON {fn}: {e}')
    return None


def region_from_place(query: str, centered: bool=True) -> Optional[Region]:
    """Resolve 'loc:PlaceName' to a bounding box."""

    from .modules.nominatim import Nominatim
    clean_q = query.split(':', 1)[1] if ':' in query else query
    nom = Nominatim(query=clean_q)
    nom.run()

    if nom.results:
        res = nom.results[0]
        x, y = res.get('x'), res.get('y')
        if x is None or y is None: return None

        if centered:
            return Region(x-.125, x+.125, y-.125, y+.125)
        else:
            x_min = math.floor(x * 4) / 4
            x_max = math.ceil(x * 4) / 4
            y_min = math.floor(y * 4) / 4
            y_max = math.ceil(y * 4) / 4
            return Region(x_min, x_max, y_min, y_max)
    return None


def parse_region(input_r: Union[str, List]) -> List[Region]:
    """Main function to parse region input into a list of Region objects."""

    regions = []
    # 1. Single String
    if isinstance(input_r, str):
        s_lower = input_r.lower()
        if s_lower.endswith(('.json', '.geojson')):
            rs = region_from_geojson(input_r)
            if rs: regions.extend(rs)
        elif s_lower.startswith(('loc:', 'place:')):
            r = region_from_place(input_r)
            if r: regions.append(r)
        else:
            r = Region.from_string(input_r)
            if r: regions.append(r)

    # 2. List/Tuple (Coordinate list OR List of strings)
    elif isinstance(input_r, (list, tuple)):
        # Check if it is a single Coordinate List [w, e, s, n]
        if len(input_r) == 4 and all(isinstance(n, (int, float)) for n in input_r):
            regions.append(Region.from_list(input_r))
        else:
            # Recursive parse for list of identifiers
            for item in input_r:
                regions.extend(parse_region(item))

    if not regions:
        # Don't warn on None input, only on failed parse of actual input
        if input_r is not None:
            logger.warning(f'Failed to parse region {input_r}')

    return regions


# =============================================================================
# Legacy / CLI Helper Functions
# =============================================================================
def fix_argparse_region(raw_argv):
    """Argument Pre-processing for negative coordinates."""

    fixed_argv = []
    i = 0
    while i < len(raw_argv):
        arg = raw_argv[i]
        if arg in ['-R', '--region', '--aoi'] and i + 1 < len(raw_argv):
            next_arg = raw_argv[i+1]
            if next_arg.startswith('-'):
                sep = '' if arg == '-R' else '='
                fixed_argv.append(f"{arg}{sep}{next_arg}")
                i += 2
                continue
        fixed_argv.append(arg)
        i += 1
    return fixed_argv


def region_valid_p(region, check_xy=True):
    """Legacy wrapper for validity check."""

    if isinstance(region, Region):
        return region.valid_p(check_xy)
    # Handle tuples via temporary Region object
    return Region.from_list(region).valid_p(check_xy) if region else False


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

# Backwards compatibility aliases
region_from_list = Region.from_list
region_from_string = Region.from_string
chunk_region = lambda r, s=1.0: Region.from_list(r).chunk(s) if r else []
buffer_region = lambda r, p=5: Region.from_list(r).buffer(p) if r else None
