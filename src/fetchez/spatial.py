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

import json
import math
import logging
import warnings
from pathlib import Path
from typing import Union, List, Tuple, Optional

from shapely.geometry import shape, box
from shapely import from_wkb
from pyproj import Transformer
from pyogrio.raw import read
from pyogrio import read_info

from fetchez.utils import str_or, _linspace

logger = logging.getLogger(__name__)


def region_help_msg():
    return """\b
Region Formats:
  xmin/xmax/ymin/ymax      : Bounding box
  loc:"City,State"         : Geocode place name
  file.geojson             : Bounding box(es) of vector file
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
        self.srs = srs

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
            return (
                self.xmin == other.xmin
                and self.xmax == other.xmax
                and self.ymin == other.ymin
                and self.ymax == other.ymax
            )
        return False

    # --- Properties ---
    @property
    def w(self):
        return self.xmin

    @property
    def e(self):
        return self.xmax

    @property
    def s(self):
        return self.ymin

    @property
    def n(self):
        return self.ymax

    @property
    def width(self):
        return abs(self.xmax - self.xmin) if self.valid_p() else 0

    @property
    def height(self):
        return abs(self.ymax - self.ymin) if self.valid_p() else 0

    @property
    def xy_region(self):
        return [self.xmin, self.xmax, self.ymin, self.ymax]

    # --- Validation ---
    def valid_p(self, check_xy: bool = True) -> bool:
        """Check if region is valid."""

        if None in [self.xmin, self.xmax, self.ymin, self.ymax]:
            return False

        try:
            if check_xy:
                if self.xmin >= self.xmax:
                    return False
                if self.ymin >= self.ymax:
                    return False
            else:
                if self.xmin > self.xmax:
                    return False
                if self.ymin > self.ymax:
                    return False
        except (ValueError, TypeError):
            return False
        return True

    is_valid = valid_p

    # --- Manipulation ---
    def copy(self):
        return Region(self.xmin, self.xmax, self.ymin, self.ymax, srs=self.srs)

    def buffer(
        self,
        pct: float = 5,
        x_bv: float | None = None,
        y_bv: float | None = None,
        x_inc: float | None = None,
        y_inc: float | None = None,
    ):
        """Buffer the region in place."""

        if not self.valid_p(check_xy=False):
            return self

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

        if x_inc is not None:
            if y_inc is None:
                y_inc = x_inc

            tmp_x_bv = int(x_bv / x_inc) * float(x_inc)
            tmp_y_bv = int(y_bv / y_inc) * float(y_inc)
            if tmp_x_bv != 0:
                x_bv = tmp_x_bv
            if tmp_y_bv != 0:
                y_bv = tmp_y_bv

        self.xmin -= x_bv
        self.xmax += x_bv
        self.ymin -= y_bv
        self.ymax += y_bv
        return self

    def center(self):
        """Return center (x, y)."""

        if not self.valid_p(check_xy=False):
            return (None, None)
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)

    def chunk(self, chunk_size: float = 1.0) -> List["Region"]:
        """Split into smaller sub-regions."""

        if not self.valid_p():
            return []

        chunks = []
        cur_w = self.xmin
        while cur_w < self.xmax:
            next_w = cur_w + chunk_size
            if next_w > self.xmax:
                next_w = self.xmax

            cur_s = self.ymin
            while cur_s < self.ymax:
                next_s = cur_s + chunk_size
                if next_s > self.ymax:
                    next_s = self.ymax

                # Check for tiny slivers
                if (next_w - cur_w > 1e-9) and (next_s - cur_s > 1e-9):
                    chunks.append(Region(cur_w, next_w, cur_s, next_s, srs=self.srs))

                cur_s = next_s
            cur_w = next_w
        return chunks

    def densify_edges(self, density=20):
        """Generate a list of points along the perimeter of the region.

        Args:
            region (Region): Input region.
            density (int): Number of points per edge.

        Returns:
            list: A list of (x, y) tuples representing the densified perimeter.
        """

        if not self.valid_p():
            return []

        xs = []
        ys = []

        ys.extend(_linspace(self.ymin, self.ymax, density))
        xs.extend([self.xmin] * density)

        xs.extend(_linspace(self.xmin, self.xmax, density))
        ys.extend([self.ymax] * density)

        ys.extend(_linspace(self.ymax, self.ymin, density))
        xs.extend([self.xmax] * density)

        xs.extend(_linspace(self.xmax, self.xmin, density))
        ys.extend([self.ymin] * density)

        # return list(zip(xs, ys))
        return xs, ys

    # --- Export Formats ---
    def to_bbox(self):
        """Export as standard (w, s, e, n) bbox used by many GIS tools."""

        return (self.xmin, self.ymin, self.xmax, self.ymax)

    def to_list(self):
        """Export as [w, e, s, n] list."""

        return [self.xmin, self.xmax, self.ymin, self.ymax]

    def format(self, style="gmt"):
        """String representation."""

        if style == "gmt":
            return f"-R{self.xmin}/{self.xmax}/{self.ymin}/{self.ymax}"
        elif style == "bbox":
            return f"{self.xmin},{self.ymin},{self.xmax},{self.ymax}"
        elif style == "region":
            return f"{self.xmin},{self.xmax},{self.ymin},{self.ymax}"
        elif style == "fn":
            ns = "s" if self.ymax < 0 else "n"
            ew = "e" if self.xmin > 0 else "w"
            return (
                f"{ns}{abs(int(self.ymax)):02d}x{abs(int(self.ymax * 100)) % 100:02d}_"
                f"{ew}{abs(int(self.xmin)):03d}x{abs(int(self.xmin * 100)) % 100:02d}"
            )
        elif style == "fn2":
            # filename safe string
            return f"w{self.xmin}_e{self.xmax}_s{self.ymin}_n{self.ymax}".replace(
                ".", "p"
            ).replace("-", "")
        elif style == "delivery":
            import datetime

            ns = "s" if self.ymax < 0 else "n"
            ew = "e" if self.xmin > 0 else "w"
            year = datetime.datetime.now().year

            coord_str = (
                f"{ns}{abs(int(self.ymax)):02d}x{abs(int(self.ymax * 100)) % 100:02d}_"
                f"{ew}{abs(int(self.xmin)):03d}x{abs(int(self.xmin * 100)) % 100:02d}"
            )
            return f"{coord_str}_{year}_v1"
        elif format == "geojson":
            geom = {
                "type": "Polygon",
                "coordinates": [
                    [
                        [self.xmin, self.ymin],
                        [self.xmin, self.ymax],
                        [self.xmax, self.ymax],
                        [self.xmax, self.ymin],
                        [self.xmin, self.ymin],
                    ]
                ],
            }
            return json.dumps(geom)
        elif format == "wkt":
            return f"POLYGON (({self.xmin} {self.ymin}, {self.xmin} {self.ymax}, {self.xmax} {self.ymax}, {self.xmax} {self.ymin}, {self.xmin} {self.ymin}))"

        return str(self)

    def to_shapely(self):
        return box(self.xmin, self.ymin, self.xmax, self.ymax)

    def to_wkt(self):
        try:
            return self.to_shapely().wkt
        except Exception:
            # Simple fallback WKT
            return (
                f"POLYGON (({self.xmin} {self.ymin}, {self.xmin} {self.ymax}, "
                f"{self.xmax} {self.ymax}, {self.xmax} {self.ymin}, "
                f"{self.xmin} {self.ymin}))"
            )

    def to_geojson_geometry(self):
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [self.xmin, self.ymin],
                    [self.xmin, self.ymax],
                    [self.xmax, self.ymax],
                    [self.xmax, self.ymin],
                    [self.xmin, self.ymin],
                ]
            ],
        }

    def srcwin(self, geo_transform, x_count, y_count, node="grid"):
        """Output the appropriate GDAL srcwin (xoff, yoff, xsize, ysize)."""

        ul = _geo2pixel(self.xmin, self.ymax, geo_transform, node=node)
        lr = _geo2pixel(self.xmax, self.ymin, geo_transform, node=node)

        x_indices = sorted([ul[0], lr[0]])
        y_indices = sorted([ul[1], lr[1]])

        x_start = max(0, x_indices[0])
        x_stop = min(x_count, x_indices[1] + 1)

        y_start = max(0, y_indices[0])
        y_stop = min(y_count, y_indices[1] + 1)

        x_size = x_stop - x_start
        y_size = y_stop - y_start

        if x_size <= 0 or y_size <= 0:
            return 0, 0, 0, 0

        return int(x_start), int(y_start), int(x_size), int(y_size)

    def geo_transform(
        self, x_inc: float = 0, y_inc: Optional[float] = None, node: str = "grid"
    ):
        """Return raster dimensions and geotransform for a region.

        Notes
        -----
        ``node="grid"`` is the historical/default convention used when deriving
        raster dimensions from geographic extents. It applies the grid-node
        rounding behavior in ``_geo2pixel`` and avoids losing a row or column when
        an extent that is mathematically an exact multiple of the resolution is
        represented slightly below that integer by floating-point arithmetic.

        ``node="pixel"`` performs direct pixel-index truncation and should not be
        substituted when calculating the dimensions of Globato processing grids.
        """

        if y_inc is None:
            y_inc = -x_inc
        elif y_inc > 0:
            y_inc = -y_inc

        dst_gt = (self.xmin, x_inc, 0, self.ymax, 0, y_inc)
        this_origin = _geo2pixel(self.xmin, self.ymax, dst_gt, node=node)
        this_end = _geo2pixel(self.xmax, self.ymin, dst_gt, node=node)

        return (
            int(this_end[0] - this_origin[0]),
            int(this_end[1] - this_origin[1]),
            dst_gt,
        )

    def geo_transform_from_count(self, x_count: int = 0, y_count: int = 0):
        x_inc = (self.xmax - self.xmin) / x_count
        y_inc = (self.ymin - self.ymax) / y_count
        dst_gt = (self.xmin, x_inc, 0, self.ymax, 0, y_inc)
        return dst_gt

    def to_geo_transform(self, nx: int, ny: int):
        """Generate a GDAL-style GeoTransform from extent and dimensions.

        Args:
        region (tuple): (min_x, min_y, max_x, max_y) - 'te' format.
        nx (int): Number of columns (x count).
        ny (int): Number of rows (y count).

        Returns:
        tuple: (top_left_x, x_res, 0, top_left_y, 0, -y_res)
        """

        x_res = (self.xmax - self.xmin) / float(nx)
        y_res = (self.ymax - self.ymin) / float(ny)
        return (self.xmin, x_res, 0, self.ymax, 0, -y_res)

    # --- Constructors ---
    @classmethod
    def from_list(cls, r_list):
        if len(r_list) < 4:
            return None
        return cls(r_list[0], r_list[1], r_list[2], r_list[3])

    @classmethod
    def from_string(cls, r_str):
        if not r_str:
            return None
        if r_str.startswith("-R"):
            r_str = r_str[2:]
        elif r_str.startswith("--region="):
            r_str = r_str.split("=")[1]

        parts = r_str.split("/")
        if len(parts) < 4:
            return None
        try:
            return cls(*[float(x) for x in parts[:4]])
        except ValueError:
            return None

    # gtl is (geo-transform, xcount, ycount)
    def from_geo_transform(cls, gtl):
        """Import a region from a geotransform list and dimensions."""

        geo_transform, x_count, y_count = gtl
        if geo_transform is not None and x_count is not None and y_count is not None:
            xmin = geo_transform[0]
            xmax = geo_transform[0] + geo_transform[1] * x_count
            ymin = geo_transform[3] + geo_transform[5] * y_count
            ymax = geo_transform[3]

            return cls(xmin, xmax, ymin, ymax)
        return None

    # --- Tranforms ---
    def transform_densify(self, transformer=None, transform_direction="FORWARD"):
        if transformer is None or not self.valid_p():
            logger.error(f"Could not perform region transformation; {self}")
            return self

        points_x, points_y = self.densify_edges(20)
        trans_points_x, trans_points_y = transformer.transform(
            points_x, points_y, direction=transform_direction
        )

        self.xmin = min(trans_points_x)
        self.xmax = max(trans_points_x)
        self.ymin = min(trans_points_y)
        self.ymax = max(trans_points_y)

        # set the new SRS
        # self.src_srs = d_srs.ExportToWkt()

        return self

    def transform(self, transformer=None, transform_direction="FORWARD"):
        if transformer is None or not self.valid_p():
            logger.error(f"Could not perform region transformation; {self}")
            return self

        self.xmin, self.ymin = transformer.transform(
            self.xmin, self.ymin, direction=transform_direction
        )
        self.xmax, self.ymax = transformer.transform(
            self.xmax, self.ymax, direction=transform_direction
        )

        return self

    def warp(self, dst_srs="epsg:4326"):
        """Transform region horizontally to a new CRS."""

        if str_or(self.srs) is None:
            logger.warning(f"Region has no valid associated srs: {self.srs}")
            return self

        if isinstance(self.srs, str) and isinstance(dst_srs, str):
            if self.srs.upper() == dst_srs.upper():
                return self

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # always_xy=True ensures we don't get tripped up by strict EPSG axis orders
            transformer = Transformer.from_crs(self.srs, dst_srs, always_xy=True)

            # Densify the edges before transforming to account for CRS curvature!
            points_x, points_y = self.densify_edges(20)
            trans_x, trans_y = transformer.transform(points_x, points_y)

            self.xmin, self.xmax = min(trans_x), max(trans_x)
            self.ymin, self.ymax = min(trans_y), max(trans_y)
            self.srs = dst_srs

            # return self.transform_densify(transformer)

        return self


# =============================================================================
# Helper / Parser Functions
# =============================================================================
def region_from_vector(fn: str, single_region: bool = False) -> Optional[List[Region]]:
    """Parse the bounding box of any OGR-supported vector file using pygorio."""

    if not Path(fn).exists():
        return None

    regions = []
    try:
        # --- Single Region for entire file ---
        if single_region:
            info = read_info(fn)
            minx, miny, maxx, maxy = info["total_bounds"]
            global_region = Region(minx, maxx, miny, maxy)

            if info.get("crs"):
                global_region.srs = info.get("crs")
                global_region.warp()

            return [global_region]

        meta, fids, geometry_wkb, fields = read(fn, columns=[])
        # --- Region for each feature in vector: ---
        if len(geometry_wkb) > 0:
            # Convert WKB directly to shapely geometries
            for geom in from_wkb(geometry_wkb):
                if geom:
                    minx, miny, maxx, maxy = geom.bounds
                    original_region = Region(minx, maxx, miny, maxy)

                    if meta.get("crs"):  # and meta.get("crs").to_epsg() != 4326:
                        original_region.srs = meta.get("crs")
                        original_region.warp()

                    regions.append(original_region)

    except Exception as e:
        logger.exception(f"Failed to parse vector bounds from {fn}: {e}")

    return regions


def region_from_geojson(fn: str) -> Optional[List[Region]]:
    """Parse the bounding box(es) of a GeoJSON file."""

    if not Path(fn).exists():
        return None

    regions = []
    try:
        with open(fn, "r") as f:
            data = json.load(f)

        features = data.get("features", [data])
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        valid = False

        for feat in features:
            geom = feat.get("geometry", feat)
            if not geom:
                continue

            b = shape(geom).bounds  # (minx, miny, maxx, maxy)
            # min_x, min_y = min(min_x, b[0]), min(min_y, b[1])
            # max_x, max_y = max(max_x, b[2]), max(max_y, b[3])
            min_x, min_y, max_x, max_y = b
            valid = True

            if not valid and "coordinates" in geom:
                xs, ys = [], []
                for x, y in _extract_coords(geom["coordinates"]):
                    xs.append(x)
                    ys.append(y)
                if xs and ys:
                    min_x, min_y = min(min_x, min(xs)), min(min_y, min(ys))
                    max_x, max_y = max(max_x, max(xs)), max(max_y, max(ys))
                    valid = True
                xs, ys = [], []

            if valid:
                regions.append(Region(min_x, max_x, min_y, max_y))

        return regions
    except Exception as e:
        logger.warning(f"Failed to parse GeoJSON {fn}: {e}")
    return None


def region_from_place(query: str, centered: bool = True) -> Optional[Region]:
    """Resolve 'loc:PlaceName' to a bounding box."""

    from .modules.nominatim import Nominatim

    clean_q = query.split(":", 1)[1] if ":" in query else query
    nom = Nominatim(query=clean_q)
    nom.run()

    if nom.results:
        res = nom.results[0]
        x, y = res.get("x"), res.get("y")
        if x is None or y is None:
            return None

        if centered:
            return Region(x - 0.125, x + 0.125, y - 0.125, y + 0.125)
        else:
            x_min = math.floor(x * 4) / 4
            x_max = math.ceil(x * 4) / 4
            y_min = math.floor(y * 4) / 4
            y_max = math.ceil(y * 4) / 4
            return Region(x_min, x_max, y_min, y_max)
    return None


def parse_region(input_r: Union[str, List]) -> List[Region]:
    """Main function to parse region input into a list of Region objects."""

    def _parse_crs(r_string: str) -> tuple[str, str | None]:
        # Parse the crs; either appended with `@` or `,`
        r_string = r_string
        target_crs = None
        if "@" in r_string:
            r_string, target_crs = r_string.split("@", 1)
        elif "," in r_string and "EPSG" in r_string.upper():
            r_string, target_crs = r_string.split(",", 1)
        return r_string, target_crs

    if not input_r:
        return []

    target_crs = None
    regions = []

    # Single String
    if isinstance(input_r, str):
        input_r, target_crs = _parse_crs(input_r)
        s_lower = input_r.lower()
        if s_lower.endswith((".json", ".geojson")):
            rs = region_from_geojson(input_r)
            if rs:
                regions.extend(rs)
        elif s_lower.endswith((".shp", ".gpkg", ".kml", ".gdb")):
            rs = region_from_vector(input_r)
            if rs:
                regions.extend(rs)
        elif s_lower.startswith(("loc:", "place:")):
            r = region_from_place(input_r)
            if r:
                r.srs = "EPSG:4326"
                regions.append(r)
        else:
            r = Region.from_string(input_r)
            r.srs = target_crs
            if r:
                regions.append(r)

    # List/Tuple (Coordinate list OR List of strings)
    elif isinstance(input_r, (list, tuple)):
        # Check if it is a single Coordinate List [w, e, s, n]
        if len(input_r) == 4 and all(isinstance(n, (int, float)) for n in input_r):
            regions.append(Region.from_list(input_r))
        else:
            # Recursive parse for list of identifiers
            for item in input_r:
                regions.extend(parse_region(item))
    elif isinstance(input_r, Region):
        regions.append(input_r.copy())

    if not regions:
        # Don't warn on None input, only on failed parse of actual input
        if input_r is not None:
            logger.warning(f"Failed to parse region {input_r}")

    return regions


def yield_parsed_regions(region_str):
    """Parses a region string, location, or vector file.

    Yields (Region, feature_name) for every region found.
    """

    if not region_str:
        yield None, None
        return

    try:
        raw_regions = parse_region(region_str)
    except Exception as e:
        logger.error(f"Error parsing region '{region_str}': {e}")
        raise

    is_batch = len(raw_regions) > 1
    for _i, r in enumerate(raw_regions):
        t_reg = Region(*r)
        # feat_name = f"tile_{i:03d}" if is_batch else None
        feat_name = t_reg.format("fn") if is_batch else None
        yield t_reg, feat_name


# =============================================================================
# Legacy / CLI Helper Functions
# =============================================================================
def fix_argparse_region(raw_argv):
    """Argument Pre-processing for negative coordinates."""

    fixed_argv = []
    i = 0
    while i < len(raw_argv):
        arg = raw_argv[i]
        if arg in ["-R", "--region", "--aoi"] and i + 1 < len(raw_argv):
            next_arg = raw_argv[i + 1]
            if next_arg.startswith("-"):
                sep = "" if arg == "-R" else "="
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

    if not region:
        return None

    west, east, south, north = region
    return box(west, south, east, north)


def region_to_wkt(region: Tuple[float, float, float, float]):
    """Convert a fetchez region (xmin, xmax, ymin, ymax) to WKT (via shapely)"""

    polygon = region_to_shapely(region)
    if polygon:
        return polygon.wkt
    else:
        w, e, s, n = region
        return f"POLYGON (({w} {s}, {w} {n}, {e} {n}, {e} {s}, {w} {s}))"


def _extract_coords(coords):
    """Recursively flatten any GeoJSON coordinate array into (x, y) tuples."""

    if not isinstance(coords, list) or not coords:
        return

    if isinstance(coords[0], (int, float)):
        yield coords[0], coords[1]
    else:
        for item in coords:
            yield from _extract_coords(item)


def region_to_bbox(region: Tuple[float, float, float, float]):
    """Convert a fetchez region to a `bbox`"""

    w, e, s, n = region
    return (w, s, e, n)


def region_to_geojson_geom(region: Tuple[float, float, float, float]):
    w, e, s, n = region
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [w, n], [e, n], [e, s], [w, s]]],
    }


# Backwards compatibility aliases
region_from_list = Region.from_list
region_from_string = Region.from_string
# chunk_region = lambda r, s=1.0: Region.from_list(r).chunk(s) if r else []
# buffer_region = lambda r, p=5: Region.from_list(r).buffer(p) if r else None


def chunk_region(r, s=1.0):
    if r:
        return Region.from_list(r).chunk(s)
    else:
        return []


def buffer_region(r, p=5):
    if r:
        return Region.from_list(r).buffer(p)
    else:
        return None


def regions_reduce(region_a: Region, region_b: Region) -> Region:
    """Combine two regions and find their minimum overlapping region."""

    region_c = Region()

    if region_a.is_valid() and region_b.is_valid():
        # Helper to get the inner bounds (max of mins, min of maxes)
        def _get_overlap(val_a, val_b, func):
            if val_a is not None and val_b is not None:
                return func(val_a, val_b)
            return None

        # Helper to merge optional fields (using first available)
        def _merge_optional(val_a, val_b, func):
            if val_a is not None and val_b is not None:
                return func(val_a, val_b)
            return val_a if val_a is not None else val_b

        region_c.xmin = _get_overlap(region_a.xmin, region_b.xmin, max)
        region_c.xmax = _get_overlap(region_a.xmax, region_b.xmax, min)
        region_c.ymin = _get_overlap(region_a.ymin, region_b.ymin, max)
        region_c.ymax = _get_overlap(region_a.ymax, region_b.ymax, min)

    return region_c


def regions_intersect_p(region_a: Region, region_b: Region) -> bool:
    """Check if two regions intersect."""

    if region_a.is_valid() and region_b.is_valid():
        reduced_region = regions_reduce(region_a, region_b)
        # Check if the overlap is valid
        if any(reduced_region.xy_region) and not reduced_region.is_valid():
            return False

    return True


# --- Geotransforms and Transformations ---
def _geo2pixel(geo_x, geo_y, geo_transform, node="grid"):
    """Convert a geographic x,y value to a pixel location."""

    if geo_transform[2] + geo_transform[4] == 0:
        pixel_x = (geo_x - geo_transform[0]) / geo_transform[1]
        pixel_y = (geo_y - geo_transform[3]) / geo_transform[5]
        if node == "grid":
            pixel_x += 0.5
            pixel_y += 0.5
    else:
        pixel_x, pixel_y = _apply_gt(geo_x, geo_y, _invert_gt(geo_transform))

    return int(pixel_x), int(pixel_y)


def _apply_gt(in_x, in_y, geo_transform, node="pixel"):
    """Apply geotransform to in_x, in_y."""

    offset = 0.5 if node == "pixel" else 0

    out_x = (
        geo_transform[0]
        + (in_x + offset) * geo_transform[1]
        + (in_y + offset) * geo_transform[2]
    )
    out_y = (
        geo_transform[3]
        + (in_x + offset) * geo_transform[4]
        + (in_y + offset) * geo_transform[5]
    )
    return out_x, out_y


def _invert_gt(geo_transform):
    """Invert the geo_transform."""

    det = (geo_transform[1] * geo_transform[5]) - (geo_transform[2] * geo_transform[4])
    if abs(det) < 1e-15:
        return None

    inv_det = 1.0 / det
    out_gt = [0.0] * 6
    out_gt[1] = geo_transform[5] * inv_det
    out_gt[4] = -geo_transform[4] * inv_det
    out_gt[2] = -geo_transform[2] * inv_det
    out_gt[5] = geo_transform[1] * inv_det
    out_gt[0] = (
        geo_transform[2] * geo_transform[3] - geo_transform[0] * geo_transform[5]
    ) * inv_det
    out_gt[3] = (
        -geo_transform[1] * geo_transform[3] + geo_transform[0] * geo_transform[4]
    ) * inv_det
    return out_gt


def x360(x):
    if x == 0:
        return -180
    elif x == 360:
        return 180
    else:
        return ((x + 180) % 360) - 180


def transform_increment(dst_inc_x, dst_inc_y, transformer, region_center):
    """Transform grid increments from Destination SRS to Source SRS.

    Args:
        dst_inc_x (float): X increment in destination units (e.g. 1/3600 for 1s).
        dst_inc_y (float): Y increment in destination units.
        transformer (pyproj.transformer.Transformer): The pipeline transforming Source -> Dest.
        region_center (tuple): (x, y) center of the region in Source CRS.

    Returns:
        (float, float): The estimated (src_inc_x, src_inc_y) in source units.
    """

    if transformer is None:
        return dst_inc_x, dst_inc_y

    cx, cy = region_center
    dest_cx, dest_cy = transformer.transform(cx, cy)
    dest_off_x = dest_cx + dst_inc_x
    dest_off_y = dest_cy + dst_inc_y

    src_off_x, _ = transformer.transform(dest_off_x, dest_cy, direction="INVERSE")
    _, src_off_y = transformer.transform(dest_cx, dest_off_y, direction="INVERSE")

    src_inc_x = abs(src_off_x - cx)
    src_inc_y = abs(src_off_y - cy)

    return src_inc_x, src_inc_y
