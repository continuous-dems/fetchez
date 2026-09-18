#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.tnm
~~~~~~~~~~~~~~~~~~~

Fetch elevation data from The National Map (TNM) API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import functools
import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

import filelock
import lxml.etree
import shapely
from pyogrio.raw import read
from pyproj import Transformer
from shapely.geometry import Polygon, box

from fetchez import cli, core, spatial, utils
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

TNM_API_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products?"
TNM_API_DATASETS_URL = "https://tnmaccess.nationalmap.gov/api/v1/datasets?"

DATASET_CODES = [
    "National Boundary Dataset (NBD)",
    "National Elevation Dataset (NED) 1 arc-second",
    "Digital Elevation Model (DEM) 1 meter",
    "National Elevation Dataset (NED) 1/3 arc-second",
    "National Elevation Dataset (NED) 1/9 arc-second",
    "National Elevation Dataset (NED) Alaska 2 arc-second",
    "Alaska IFSAR 5 meter DEM",
    "National Elevation Dataset (NED) 1/3 arc-second - Contours",
    "Original Product Resolution (OPR) Digital Elevation Model (DEM)",
    "Ifsar Digital Surface Model (DSM)",
    "Ifsar Orthorectified Radar Image (ORI)",
    "Lidar Point Cloud (LPC)",
    "Historical Topographic Maps",
    "National Hydrography Dataset Plus High Resolution (NHDPlus HR)",
    "National Hydrography Dataset (NHD) Best Resolution",
    "National Watershed Boundary Dataset (WBD)",
    "Map Indices",
    "National Geographic Names Information System (GNIS)",
    "Small-scale Datasets - Boundaries",
    "Small-scale Datasets - Contours",
    "Small-scale Datasets - Hydrography",
    "Small-scale Datasets - Transportation",
    "National Structures Dataset (NSD)",
    "Combined Vector",
    "National Transportation Dataset (NTD)",
    "US Topo Current",
    "US Topo Historical",
    "Land Cover - Woodland",
    "3D Hydrography Program (3DHP)",
    "Seamless 1-m DEM (S1M)",
]
DATASET_ALIASES = {
    "1m": 2,
    "1_9as": 4,
    "1_3as": 3,
    "1_as": 1,
    "2_as": 5,
    "5m": 6,
    "s1m": 29,
}
DATASET_PRODUCTS = {
    DATASET_CODES[index]: alias for alias, index in DATASET_ALIASES.items()
}


class TNMApiError(RuntimeError):
    """The TNM API gave no usable answer (as opposed to answering "no products")."""


# =============================================================================
# Fallback discovery (used only when the TNM API fails)
# =============================================================================
# USGS stages its elevation products in a public S3 bucket, and the bucket
# listing can stand in for the products API. Products found here carry the same
# `url` and filename the API returns, so cached files are reused either way.
TNM_S3_URL = "https://prd-tnm.s3.amazonaws.com/"
S3_ELEVATION_PREFIX = "StagedProducts/Elevation/"

# dataset -> (S3 directory, label used in titles, tile overlap in degrees)
NED_S3_LAYOUT = {
    DATASET_CODES[1]: ("1", "1 Arc Second", 6 / 3600),
    DATASET_CODES[3]: ("13", "1/3 Arc Second", 6 / 10800),
}


def _s3_list(prefix):
    """List `(key, size, last_modified)` for every object under a prd-tnm prefix.

    An empty listing is a valid answer (nothing staged there, e.g. an ocean
    cell). Anything that is not a complete S3 listing raises, so an outage is
    never mistaken for "no data".
    """

    found = []
    token = None
    while True:
        params = {"list-type": 2, "prefix": prefix}
        if token:
            params["continuation-token"] = token

        req = core.Fetch(TNM_S3_URL).fetch_req(params=params)
        if req is None or req.status_code != 200:
            status = req.status_code if req is not None else "no response"
            raise RuntimeError(f"S3 listing failed for {prefix}: {status}")

        try:
            root = lxml.etree.fromstring(req.content)
        except lxml.etree.XMLSyntaxError as e:
            raise RuntimeError(f"S3 listing for {prefix} is not XML") from e
        if lxml.etree.QName(root).localname != "ListBucketResult":
            raise RuntimeError(f"S3 listing for {prefix} is not a bucket listing")

        for item in root.findall("{*}Contents"):
            found.append(
                (
                    item.findtext("{*}Key"),
                    int(item.findtext("{*}Size")),
                    item.findtext("{*}LastModified"),
                )
            )

        if root.findtext("{*}IsTruncated") != "true":
            return found
        token = root.findtext("{*}NextContinuationToken")
        if not token:
            raise RuntimeError(f"S3 listing for {prefix} was cut short")


def _ned_cells(w, e, s, n, pad):
    """Yield `(name, west, south)` for each 1-degree NED cell a region touches.

    A cell is named for its north-west corner: n35w121 spans 34-35N, 121-120W.
    The region is grown by the tile overlap, as the API's bounding-box test
    also matches a neighbour whose overlap reaches into the region.
    """

    for south in range(math.floor(s - pad), math.ceil(n + pad)):
        for west in range(math.floor(w - pad), math.ceil(e + pad)):
            north = south + 1
            ns = "n" if north >= 0 else "s"
            ew = "w" if west < 0 else "e"
            yield f"{ns}{abs(north):02d}{ew}{abs(west):03d}", west, south


def _ned_products(module, dataset):
    """Find seamless NED products (1 or 1/3 arc-second) from the S3 listing.

    The API returns every dated version under `historical/` and never the
    undated copy under `current/`, which is the same file as the newest dated
    one. `current/` is only used for a cell that has no dated version.
    """

    res, label, pad = NED_S3_LAYOUT[dataset]
    w, e, s, n = module.wgs_region
    products = []
    for cell, west, south in _ned_cells(w, e, s, n, pad):
        tifs = []
        for sub in ("historical", "current"):
            prefix = f"{S3_ELEVATION_PREFIX}{res}/TIFF/{sub}/{cell}/"
            tifs = [obj for obj in _s3_list(prefix) if obj[0].endswith(".tif")]
            if tifs:
                break

        bounds = (west - pad, west + 1 + pad, south - pad, south + 1 + pad)
        for key, size, modified in tifs:
            filename = key.rsplit("/", 1)[-1]
            stamp = re.search(r"_(\d{4})(\d{2})(\d{2})\.tif$", filename)
            date = "-".join(stamp.groups()) if stamp else (modified or "")[:10]
            version = f" {''.join(stamp.groups())}" if stamp else ""
            products.append(
                {
                    "url": TNM_S3_URL + quote(key),
                    "filename": filename,
                    "format": "GeoTIFF",
                    "bounds": bounds,
                    "date": date,
                    "remote_size": size,
                    "title": f"USGS {label} {cell}{version}",
                }
            )
    return products


# -----------------------------------------------------------------------------
# DEM 1 meter: which projects cover the region, then each project's S3 folder
# -----------------------------------------------------------------------------
# Two sources say which projects cover a region, with the same fields: the
# ArcGIS 3DEP Elevation Index, and FESM_1m.gpkg, a ~2 GB file of the same project
# outlines that is downloaded once and then read locally.
TNM_INDEX_1M_URL = (
    "https://index.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevationIndex/MapServer/18/query"
)
FESM_1M_KEY = S3_ELEVATION_PREFIX + "1m/FullExtentSpatialMetadata/FESM_1m.gpkg"
FESM_1M_FILENAME = "FESM_1m.gpkg"
# The file is rewritten every few days; an older copy still lists nearly every
# project, so it is only replaced once it is both outdated and this old.
FESM_MAX_AGE_DAYS = 30

# USGS_1M_10_x54y415_<project>.tif, USGS_one_meter_x37y372_<project>.tif and
# USGS_1m_x14y199_<project>.tif: x/y are the tile's north-west corner in units of
# 10 km (NAD83 UTM), and every tile carries a 6 m collar. The zone is only in
# the newest style of name.
TILE_1M_NAME = re.compile(r"^USGS_(?:1[Mm]|one_meter)_(?:(\d{1,2})_)?x(\d+)y(\d+)_")
TILE_1M_SIZE = 10000
TILE_1M_COLLAR = 6
TILE_1M_EDGE_TOLERANCE = 0.001  # degrees, about 100 m
INDEX_1M_MARGIN = 0.15  # degrees; a 10 km tile is up to 0.14 wide at 49N


def _iso_date(value):
    """'8/25/2025' (ArcGIS), a date/datetime64 (GeoPackage) or epoch ms -> 'YYYY-MM-DD'."""

    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return time.strftime("%Y-%m-%d", time.gmtime(value / 1000))
    text = str(value)
    us_style = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if us_style:
        month, day, year = us_style.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def _project_prefix(link):
    """S3 prefix of a project folder, from the index's `product_link`.

    The link is followed rather than the project name, as the two can differ
    (CA_SoCAL_Wildfires_2018_D18 is staged under CA_SoCal_Wildfires_B4_2018).
    ArcGIS writes it as `.../index.html?prefix=<prefix>`, FESM as `.../<prefix>`.
    """

    parts = urlsplit(link or "")
    prefix = parse_qs(parts.query).get("prefix", [""])[0] or unquote(parts.path)
    prefix = prefix.strip("/")
    if not re.search(r"/Projects/[^/]+", prefix):
        return None
    return prefix + "/"


def _keep_project(projects, link, pub_date):
    """Record one index row. A row without a usable link cannot be followed, and
    skipping it would hide data, so the caller is told to use another index."""

    prefix = _project_prefix(link)
    if prefix is None:
        raise RuntimeError("the project index lists a project here without a link")
    projects[prefix] = max(projects.get(prefix, ""), _iso_date(pub_date))


def _arcgis_1m_projects(w, e, s, n):
    """`{S3 prefix: publication date}` for the 1 m projects touching a region."""

    projects = {}
    offset = 0
    while True:
        params = {
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "pub_date,product_link",
            "returnGeometry": "false",
            "resultOffset": offset,
            "f": "json",
        }
        req = core.Fetch(TNM_INDEX_1M_URL).fetch_req(params=params)
        if req is None or req.status_code != 200:
            status = req.status_code if req is not None else "no response"
            raise RuntimeError(f"3DEP Elevation Index request failed: {status}")
        try:
            data = req.json()
        except Exception as exc:
            raise RuntimeError("3DEP Elevation Index returned invalid JSON") from exc
        # ArcGIS reports its own errors as HTTP 200 with an `error` member.
        if not isinstance(data, dict) or "error" in data or "features" not in data:
            raise RuntimeError("3DEP Elevation Index returned an error")

        features = data["features"]
        for feature in features:
            attrs = feature.get("attributes", {})
            _keep_project(projects, attrs.get("product_link"), attrs.get("pub_date"))

        if not data.get("exceededTransferLimit"):
            return projects
        if not features:
            raise RuntimeError("3DEP Elevation Index paging stopped early")
        offset += len(features)


def _fesm_projects(path, w, e, s, n):
    """The same answer as `_arcgis_1m_projects`, read from a local FESM_1m.gpkg."""

    meta, _fids, geometry, fields = read(
        str(path), bbox=(w, s, e, n), columns=["pub_date", "product_link"]
    )
    names = list(meta["fields"])
    dates = fields[names.index("pub_date")]
    links = fields[names.index("product_link")]
    roi = box(w, s, e, n)
    projects = {}
    # `bbox` matches on envelopes; the outlines are far from rectangular.
    for wkb, pub_date, link in zip(geometry, dates, links, strict=True):
        if wkb is not None and shapely.from_wkb(wkb).intersects(roi):
            _keep_project(projects, link, pub_date)
    return projects


def _fesm_remote():
    """Size and modification time of FESM_1m.gpkg on S3: its change token."""

    for key, size, modified in _s3_list(FESM_1M_KEY):
        if key == FESM_1M_KEY:
            return {"size": size, "last_modified": modified}
    raise RuntimeError(f"{FESM_1M_FILENAME} is not staged on S3")


def _fesm_state(path):
    """'current', 'newer-exists', 'outdated' or 'unchecked' for a local FESM_1m.gpkg."""

    try:
        remote = _fesm_remote()
    except Exception as e:
        logger.warning(f"Could not check {FESM_1M_FILENAME} against S3: {e}")
        return "unchecked"

    sidecar = Path(f"{path}.meta.json")
    try:
        recorded = json.loads(sidecar.read_text())
    except (OSError, ValueError):
        # A copy placed here by hand has no record; its size identifies it.
        recorded = {}
        if path.stat().st_size == remote["size"]:
            recorded = remote
            sidecar.write_text(json.dumps(remote))

    if recorded == remote:
        return "current"
    age_days = (time.time() - path.stat().st_mtime) / 86400
    return "outdated" if age_days > FESM_MAX_AGE_DAYS else "newer-exists"


def _fesm_download(path):
    remote = _fesm_remote()
    logger.info(
        f"1 m project index: downloading {FESM_1M_FILENAME} "
        f"({remote['size'] / 1e9:.1f} GB, one time)"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    status = core.Fetch(TNM_S3_URL + FESM_1M_KEY).fetch_file(path, verbose=True)
    if status != 0 or not path.exists() or path.stat().st_size != remote["size"]:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"{FESM_1M_FILENAME} download failed or is incomplete")
    Path(f"{path}.meta.json").write_text(json.dumps(remote))


def _local_fesm(module, download=False):
    """Path of a usable local FESM_1m.gpkg, or None.

    With `download`, a missing or outdated copy is fetched. Parallel runs sharing
    a cache take turns here, so the file is downloaded once and not once each.
    """

    path = Path(module._outdir) / FESM_1M_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with filelock.FileLock(f"{path}.refresh.lock", timeout=7200):
        if path.exists() and path.stat().st_size > 0:
            state = _fesm_state(path)
            when = time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))
            if state == "newer-exists":
                logger.info(
                    f"A newer {FESM_1M_FILENAME} exists; using the local copy from {when}."
                )
            if state == "unchecked":
                logger.warning(f"Using the local {FESM_1M_FILENAME} from {when}.")
            if state != "outdated":
                logger.info(f"1 m project index: local {FESM_1M_FILENAME} ({when})")
                return path
            # Having the file at all means this cache is meant to work offline.
            download = True

        if not download:
            return None
        _fesm_download(path)
        logger.info(f"1 m project index: local {FESM_1M_FILENAME} (just downloaded)")
        return path


def _projects_1m(module):
    """Local FESM if there is one, else ArcGIS, else download FESM and use that."""

    # The API matches on tile rectangles, which reach past a project's outline by
    # up to a tile's width; ask the index about that much more ground. Listing a
    # project that turns out to have no tile here costs one S3 request.
    w, e, s, n = module.wgs_region
    w, e, s, n = (
        w - INDEX_1M_MARGIN,
        e + INDEX_1M_MARGIN,
        s - INDEX_1M_MARGIN,
        n + INDEX_1M_MARGIN,
    )
    try:
        path = _local_fesm(module)
        if path is not None:
            return _fesm_projects(path, w, e, s, n)
    except Exception as exc:
        logger.warning(f"Local {FESM_1M_FILENAME} could not be used: {exc}")

    try:
        projects = _arcgis_1m_projects(w, e, s, n)
        logger.info("1 m project index: ArcGIS 3DEP Elevation Index")
        return projects
    except Exception as exc:
        logger.warning(
            f"ArcGIS 3DEP Elevation Index unavailable ({exc}); "
            f"using {FESM_1M_FILENAME} instead."
        )
    return _fesm_projects(_local_fesm(module, download=True), w, e, s, n)


def _utm_zone(lon):
    return min(60, max(1, int((lon + 180) // 6) + 1))


@functools.cache
def _utm_to_lonlat(zone):
    # NAD83 has UTM zones 1-23; elsewhere (Guam) WGS84 is within a metre or two.
    epsg = 26900 + zone if zone <= 23 else 32600 + zone
    return Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)


def _utm_tile_footprint(zone, x, y):
    """Lon/lat outline of a 1 m tile, from the numbers in its file name.

    All four corners are transformed: a UTM square is not a lon/lat rectangle.
    """

    west = x * TILE_1M_SIZE - TILE_1M_COLLAR
    east = (x + 1) * TILE_1M_SIZE + TILE_1M_COLLAR
    north = y * TILE_1M_SIZE + TILE_1M_COLLAR
    south = (y - 1) * TILE_1M_SIZE - TILE_1M_COLLAR
    corners = [(west, north), (east, north), (east, south), (west, south)]
    return Polygon([_utm_to_lonlat(zone).transform(*corner) for corner in corners])


def _dem_1m_products(module, dataset):
    """Find project-based 1 m DEM tiles: project index, then each project's S3 folder."""

    w, e, s, n = module.wgs_region
    # The API's own edge test is looser than the bounds it reports (it returns
    # tiles some 30 m outside the query box), so lean towards one tile too many.
    roi = box(w, s, e, n).buffer(TILE_1M_EDGE_TOLERANCE)
    # A project can carry one zone's grid past the 6-degree line (western Puerto
    # Rico is gridded in zone 20), so a name without a zone is tried in the
    # neighbouring zones too.
    nearby_zones = [
        z for z in range(_utm_zone(w) - 1, _utm_zone(e) + 2) if 1 <= z <= 60
    ]

    products = []
    for prefix, pub_date in sorted(_projects_1m(module).items()):
        for key, size, modified in _s3_list(prefix + "TIFF/"):
            if not key.lower().endswith(".tif"):
                continue
            filename = key.rsplit("/", 1)[-1]
            item = {
                "url": TNM_S3_URL + quote(key),
                "filename": filename,
                "format": "GeoTIFF",
                "date": pub_date or (modified or "")[:10],
                "remote_size": size,
                "title": filename.rsplit(".", 1)[0].replace("_", " "),
            }

            named = TILE_1M_NAME.match(filename)
            if named:
                zone, x, y = named.groups()
                zones = [int(zone)] if zone else nearby_zones
                # Like the API, match and describe a tile by its lon/lat rectangle.
                rectangles = [
                    box(*_utm_tile_footprint(z, int(x), int(y)).bounds) for z in zones
                ]
                hit = next((r for r in rectangles if r.intersects(roi)), None)
                if hit is None:
                    continue
                west, south, east, north = hit.bounds
                item["bounds"] = (west, east, south, north)
            else:
                # Never drop a file silently; without a position it cannot be culled.
                logger.warning(
                    f"Cannot read a tile position from {filename}; "
                    "keeping it without a footprint."
                )
            products.append(item)
    return products


# dataset -> (where the fallback looks, function(module, dataset) -> products)
# TODO(tnm-fallback): datasets with no fallback yet, and what each would need:
#   - NED 1/9 arc-second: staged as IMG under Elevation/19/IMG/, not GeoTIFF;
#     file naming still to be checked against API answers.
#   - NED Alaska 2 arc-second: only Elevation/2/TIFF/historical/ found so far.
#   - Alaska IFSAR 5 meter: project directories under Elevation/OPR/Projects/.
#   - Seamless 1-m DEM (S1M): the USGS_Seamless1m_Index service lists tiles but
#     most of its attributes are empty today.
#   - OPR, LPC and the non-elevation datasets: not investigated.
FALLBACK_DISCOVERY = {
    DATASET_CODES[1]: ("the prd-tnm S3 listing", _ned_products),
    DATASET_CODES[2]: (
        "the 3DEP project index and the prd-tnm S3 listing",
        _dem_1m_products,
    ),
    DATASET_CODES[3]: ("the prd-tnm S3 listing", _ned_products),
}


# =============================================================================
# The National Map Module
# =============================================================================
@cli.cli_opts(
    help_text="USGS The National Map (TNM) Elevation Products",
    datasets="Slash-separated indices of datasets to fetch (e.g. '1/3')",
    formats="Filter by file format (e.g. GeoTIFF, LAZ)",
    extents="Filter by extent (e.g. '1 x 1 degree')",
    q="Free text search query",
    date_start="Start date (YYYY-MM-DD)",
    date_end="End date (YYYY-MM-DD)",
    products="Elevation products: s1m/1m/1_9as/1_3as/1_as/5m/2_as (strict queries)",
    strict_datasets="Raise on rejected or incomplete queries instead of returning partial results",
)
class TheNationalMap(FetchModule):
    name = "tnm"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Products (NED, Lidar, Hydro) via The National Map"
    meta_agency = "USGS"
    meta_tags = ["usgs", "ned", "3dep", "lidar", "usa", "elevation"]
    meta_region = "USA"
    meta_resolution = "Varies (1m - 1 arc-second)"
    meta_license = "Public Domain (USGS)"
    meta_urls = {
        "home": "https://apps.nationalmap.gov/",
        "api": "https://tnmaccess.nationalmap.gov/api/v1/docs/",
    }

    """Fetch elevation data from The National Map.

    Default behavior fetches 'NED 1 arc-second' if no dataset is specified.

    Dataset Codes (indices for --datasets):
      1: NED 1 arc-second
      2: DEM 1 meter
      3: NED 1/3 arc-second
      4: NED 1/9 arc-second
      8: Original Product Resolution (OPR)
      11: Lidar Point Cloud (LPC)
    """

    def __init__(
        self,
        datasets: Optional[str] = None,
        formats: Optional[str] = None,
        extents: Optional[str] = None,
        q: Optional[str] = None,
        date_type: Optional[str] = "dateCreated",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        products: str | Sequence[str] | None = None,
        strict_datasets: bool = False,
        **kwargs,
    ):
        super().__init__(name="tnm", **kwargs)
        self.q = q
        self.formats = formats
        self.extents = extents
        self.datasets = str(datasets)
        self.date_type = date_type
        self.date_start = date_start
        self.date_end = date_end
        self.products = None
        if products is not None:
            if datasets is not None:
                raise ValueError("Use either products or datasets, not both")
            selected = utils.parse_arg_to_list(
                products if isinstance(products, (str, list)) else list(products), str
            )
            self.products = list(
                dict.fromkeys(str(value).lower() for value in selected)
            )
            if not self.products or any(
                value not in DATASET_ALIASES for value in self.products
            ):
                raise ValueError(f"Unknown TNM products: {products}")
        self.strict_datasets = self.products is not None or bool(
            utils.str2bool(strict_datasets)
        )

    def run(self):
        """Run the TNM fetching module."""

        if self.wgs_region is None or not spatial.region_valid_p(self.wgs_region):
            return []

        # Determine Datasets to query
        dataset_names = []
        if self.products is not None:
            dataset_names = [
                DATASET_CODES[DATASET_ALIASES[value]] for value in self.products
            ]
        elif self.datasets not in (None, "None"):
            try:
                ds_indices = []
                for x in self.datasets.split("/"):
                    if x.lower() in DATASET_ALIASES:
                        ds_indices.append(DATASET_ALIASES[x.lower()])
                    else:
                        ds_indices.append(int(x))
                if self.strict_datasets and any(
                    i < 0 or i >= len(DATASET_CODES) for i in ds_indices
                ):
                    raise ValueError("Dataset index out of range")
                dataset_names = [
                    DATASET_CODES[i] for i in ds_indices if 0 <= i < len(DATASET_CODES)
                ]
            except (ValueError, IndexError):
                if self.strict_datasets:
                    raise ValueError(f"Invalid TNM datasets: {self.datasets}") from None
                logger.warning(
                    f"Could not parse datasets '{self.datasets}'. Using default."
                )

        if not dataset_names:
            dataset_names = ["National Elevation Dataset (NED) 1 arc-second"]

        start = len(self.results)
        try:
            # Query products separately so each entry has an unambiguous product label.
            if self.products is not None:
                for dataset in dataset_names:
                    self._run_query([dataset])
            else:
                self._run_query(dataset_names)
        except Exception:
            del self.results[start:]
            raise
        return self

    def _run_query(self, dataset_names):
        """Ask the API; if it gives no usable answer, find the products another way."""

        start = len(self.results)
        try:
            return self._query_api(dataset_names)
        except TNMApiError as e:
            # Never keep half an answer: a partial list would be cached as complete.
            del self.results[start:]
            self._discover_without_api(dataset_names, reason=str(e)[:200])
        return self

    def _discover_without_api(self, dataset_names, reason):
        """Fallback discovery for the datasets that have one; a logged error otherwise."""

        problem = None
        missing = [name for name in dataset_names if name not in FALLBACK_DISCOVERY]
        formats = {f.lower() for f in (self.formats or "").split("/") if f}
        if missing:
            problem = f"no fallback discovery exists for {', '.join(missing)}"
        elif self.q or self.extents or self.date_start:
            problem = "fallback discovery cannot apply q, extents or date filters"
        elif formats - {"geotiff"}:
            problem = f"fallback discovery only finds GeoTIFF, not {self.formats}"

        if problem is None:
            sources = list(
                dict.fromkeys(FALLBACK_DISCOVERY[name][0] for name in dataset_names)
            )
            logger.warning(
                f"TNM API unavailable ({reason}). Using fallback discovery for "
                f"{', '.join(dataset_names)} via {' and '.join(sources)}; "
                "results may differ slightly from the API's."
            )
            start = len(self.results)
            # The API labels an entry with its product only when one dataset was queried.
            dataset = dataset_names[0] if len(dataset_names) == 1 else None
            try:
                for name in dataset_names:
                    source, find = FALLBACK_DISCOVERY[name]
                    found = find(self, name)
                    for item in found:
                        self._add_product(dataset=dataset, tnm_discovery=source, **item)
                    logger.info(
                        f"Fallback discovery found {len(found)} product(s) for {name}."
                    )
                return
            except Exception as e:
                del self.results[start:]
                problem = f"fallback discovery failed: {e}"

        logger.error(
            f"TNM API unavailable ({reason}) and {problem}. "
            "No products returned; this result is not cached."
        )
        self._discovery_failed = True
        if self.strict_datasets:
            raise TNMApiError(f"TNM API unavailable ({reason}) and {problem}")

    def _add_product(self, url, filename, dataset=None, **fields):
        """Add one product entry; shared by the API and fallback paths so both name files alike."""

        path = urlsplit(url).path
        product = DATASET_PRODUCTS.get(dataset)
        project = None
        if "/Projects/" in path:
            project = unquote(path.split("/Projects/", 1)[1].split("/", 1)[0])

        dst_fn = filename
        if self.products is not None:
            # Different projects/versions can share a filename.
            digest = hashlib.sha256(url.encode()).hexdigest()[:12]
            dst_fn = f"{product}/{digest}/{filename}"

        bounds = fields.pop("bounds", None)
        geom = box(bounds[0], bounds[2], bounds[1], bounds[3]) if bounds else None
        geom = fields.pop("geometry", geom)

        self.add_entry_to_results(
            url=url,
            dst_fn=dst_fn,
            data_type="tnm",
            bounds=bounds,
            geometry=geom,
            tnm_project=project,
            tnm_product=product,
            tnm_dataset=dataset,
            **fields,
        )

    def _query_api(self, dataset_names):
        w, e, s, n = self.wgs_region
        bbox_str = f"{w},{s},{e},{n}"
        offset = 0
        expected_total = None
        seen_urls = set()
        dataset = dataset_names[0] if len(dataset_names) == 1 else None

        while True:
            params = {
                "bbox": bbox_str,
                "max": 100,
                "offset": offset,
                "datasets": ",".join(dataset_names),
            }

            if self.q:
                params["q"] = str(self.q)
            if self.formats:
                params["prodFormats"] = self.formats.replace("/", ",")
            if self.extents:
                params["prodExtents"] = self.extents.replace("/", ",")

            if self.date_start:
                params["start"] = self.date_start
                params["end"] = (
                    self.date_end if self.date_end else utils.this_date()[:8]
                )
                params["dateType"] = self.date_type

            req = core.Fetch(TNM_API_PRODUCTS_URL).fetch_req(params=params)

            if (
                req is not None
                and "All dataset queries failed" in req.text
                and "datasets" in params
            ):
                if self.strict_datasets:
                    raise TNMApiError("TNM API rejected the requested dataset")
                logger.warning(
                    "USGS rejected the strict dataset strings. Retrying with broad text search..."
                )

                params.pop("datasets")

                fallback_q = params.get("q", "") + " " + " ".join(dataset_names)
                fallback_q = fallback_q.replace(
                    "National Elevation Dataset (NED)", ""
                ).strip()
                params["q"] = fallback_q

                req = core.Fetch(TNM_API_PRODUCTS_URL).fetch_req(params=params)
                # A broad text search cannot establish a specific product identity.
                dataset = None

            if req is None or req.status_code != 200:
                status = req.status_code if req is not None else "no response"
                raise TNMApiError(f"TNM API request failed: {status}")

            if req.text.strip().startswith("{errorMessage"):
                raise TNMApiError(f"TNM API error: {req.text}")

            try:
                data = req.json()
                # An outage can answer HTTP 200 with {"error": ...}; without this
                # check that reads as "no products" and gets cached as such.
                if (
                    not isinstance(data, dict)
                    or "error" in data
                    or "total" not in data
                    or "items" not in data
                ):
                    raise TNMApiError(
                        f"TNM API returned an error body: {req.text.strip()[:120]}"
                    )
                total = data.get("total", 0)
                items = data.get("items", [])
                if self.strict_datasets:
                    if (
                        data.get("errorMessage")
                        or "total" not in data
                        or "items" not in data
                        or not isinstance(total, int)
                        or total < 0
                        or not isinstance(items, list)
                        or offset + len(items) > total
                        or (offset < total and not items)
                    ):
                        raise ValueError(
                            "TNM API returned an incomplete or invalid page"
                        )
                    if expected_total is not None and total != expected_total:
                        raise ValueError("TNM result total changed during pagination")
                    expected_total = total

                for item in items:
                    url = item.get("downloadURL")
                    if not url:
                        if self.strict_datasets:
                            raise ValueError("TNM product has no download URL")
                        continue
                    if self.strict_datasets:
                        if url in seen_urls:
                            raise ValueError(
                                "TNM API repeated a download URL during pagination"
                            )
                        seen_urls.add(url)

                    item_bbox = item.get("boundingBox", {})
                    bounds = None
                    if item_bbox:
                        bounds = (
                            item_bbox.get("minX"),
                            item_bbox.get("maxX"),
                            item_bbox.get("minY"),
                            item_bbox.get("maxY"),
                        )

                    self._add_product(
                        url=url,
                        filename=urlsplit(url).path.rsplit("/", 1)[-1],
                        dataset=dataset,
                        format=item.get("format", "Unknown"),
                        bounds=bounds,
                        date=item.get("publicationDate", ""),
                        remote_size=item.get("sizeInBytes"),
                        title=item.get("title"),
                        tnm_source_id=item.get("sourceId"),
                        tnm_publication_date=item.get("publicationDate"),
                        tnm_last_updated=item.get("lastUpdated"),
                        tnm_meta_url=item.get("metaUrl"),
                        tnm_vendor_meta_url=item.get("vendorMetaUrl"),
                    )

            except TNMApiError:
                raise
            except Exception as e:
                raise TNMApiError(f"Unable to complete TNM discovery: {e}") from e

            offset += len(items) if self.strict_datasets else 100
            if offset >= total:
                break

        return self


# =============================================================================
# Shortcuts (Subclasses)
# =============================================================================
@cli.cli_opts(
    help_text="National Elevation Dataset (NED) / 3DEP DEMs",
    res="Resolution: '13' (Default: 1 & 1/3 arc-sec), '1m' (1-meter), '1', '1/3', or 'all'",
)
class NED(TheNationalMap):
    name = "ned"
    meta_category = "Topography"
    meta_desc = 'USGS Seamless DEMs (1m, 1/3", 1")'
    meta_aliases = ["3dep_dem", "NED"]

    """
    Shortcut for fetching USGS NED / 3DEP DEMs at various resolutions.

    Resolutions (--res):
      13    : Fetch both 1 arc-second and 1/3 arc-second (Default)
      1m    : Fetch 1-meter DEMs (High Res)
      1/3   : Fetch 1/3 arc-second only
      1     : Fetch 1 arc-second only
      all   : Fetch 1 arc-sec, 1/3 arc-sec, AND 1-meter
    """

    def __init__(self, res: str = "13", **kwargs):
        # Map resolution strings to TNM Dataset Indices
        # 1 = NED 1 arc-sec
        # 2 = DEM 1 meter
        # 3 = NED 1/3 arc-sec

        mapping = {
            "13": "1/3",  # Standard seamless (Old Default)
            "1m": "2",  # High res
            "1": "1",  # Coarse
            "1/3": "3",  # Standard
            "all": "1/2/3",  # Everything
        }

        selected_datasets = mapping.get(res, "1/3")

        super().__init__(datasets=selected_datasets, **kwargs)


@cli.cli_opts(help_text="USGS 3DEP Lidar Point Clouds (LAZ)")
class TNM_LAZ(TheNationalMap):
    name = "3dep"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Lidar Point Clouds (LAZ)"
    meta_aliases = ["3dep_lidar"]

    """Shortcut for fetching Lidar Point Clouds (LAZ)."""

    def __init__(self, **kwargs):
        # Index 11 (LPC) + Format Filter
        super().__init__(datasets="11", formats="LAZ", **kwargs)
