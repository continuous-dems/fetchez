#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.modules.stac
~~~~~~~~~~~~~~~~~~~~~

Generic STAC API discovery for Fetchez.

Requires: pip install pystac-client
Optional: pip install planetary-computer boto3

Example catalogs (collection IDs and access policies vary):
  Earth Search: https://earth-search.aws.element84.com/v1
  Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1
  NASA CMR (provider-specific): https://cmr.earthdata.nasa.gov/stac
  Copernicus Data Space: https://stac.dataspace.copernicus.eu/v1/

STAC discovery returns regular Fetchez entries. Signed URLs can expire and
should not be reused indefinitely from a discovery cache. Disable discovery
caching for authenticated/presigned assets until acquisition-time signing is
available in the fetching layer.
"""

import json
import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from fetchez import cli
from fetchez.modules import FetchModule

try:
    import pystac_client
except ImportError:
    pystac_client = None
try:
    import planetary_computer
except ImportError:
    planetary_computer = None
try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


def _list(value):
    """Normalize CLI CSV or YAML list to a list of strings."""
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            value = json.loads(stripped)
        else:
            value = stripped.split(",")

    if not isinstance(value, (list, tuple, set)):
        raise ValueError("Expected a comma-separated string or list")

    return [str(v).strip() for v in value if str(v).strip()]


def _mapping(value, field):
    if value is None:
        return None

    if isinstance(value, str):
        value = json.loads(value)

    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object or mapping")

    return value


def _safe(value):
    return (
        re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "unknown")).strip("._")[:150]
        or "unknown"
    )


def _extension(href, media_type):
    path = urlsplit(href).path
    name = Path(path).name
    if name.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".copc.laz")):
        return "".join(Path(name).suffixes[-2:])

    ext = Path(name).suffix
    if ext:
        return ext

    if media_type:
        mime = media_type.split(";", 1)[0].lower()
        known = {
            "image/tiff": ".tif",
            "image/geotiff": ".tif",
            "application/geo+json": ".geojson",
            "application/geojson": ".geojson",
            "application/json": ".json",
            "application/x-netcdf": ".nc",
            "application/vnd.laszip+copc": ".copc.laz",
        }
        return known.get(mime) or mimetypes.guess_extension(mime) or ""
    return ""


def _infer_type(ext, media_type):
    ext = ext.lower()
    if ext in {".tif", ".tiff", ".nc", ".h5", ".hdf", ".grib", ".grb"}:
        return "raster"
    if ext in {".laz", ".las", ".copc.laz"}:
        return "point_cloud"
    if ext in {".gpkg", ".shp", ".geojson", ".fgb"}:
        return "vector"
    if ext in {".zip", ".gz", ".tar", ".7z"}:
        return "archive"
    if ext == ".json" or (media_type or "").split(";")[0] == "application/json":
        return "json"
    return "file"


def _s3_public_url(href):
    parts = urlsplit(href)
    bucket, key = parts.netloc, parts.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 asset URI: {href}")

    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


@cli.cli_opts(
    help_text="Discover assets from a STAC API (Earth Search, Planetary Computer, etc.).",
    url="STAC API root URL.",
    collections="Collection IDs: CSV string or YAML list.",
    assets="Asset keys: CSV/list; all selects every asset.",
    asset_roles="Optional STAC asset roles (CSV/list).",
    asset_media_types="Optional asset media types (CSV/list).",
    date="Datetime or interval (e.g. 2025-01-01/2025-02-01).",
    cloud_cover="Optional maximum eo:cloud_cover percentage.",
    query="STAC Query extension JSON mapping.",
    filter="CQL2 filter (mapping or text, if supported by API).",
    filter_lang="CQL2 filter language, if needed.",
    ids="Optional item IDs, CSV/list.",
    sign="auto, planetary_computer, s3, or none.",
    data_type="Override inferred Fetchez entry type.",
    limit="Maximum number of STAC items (not assets).",
)
class STACModule(FetchModule):
    name = "stac"
    meta_category = "Generic"
    meta_desc = "Generic STAC API discovery (SpatioTemporal Asset Catalog)"
    meta_agency = "Various"
    meta_tags = ["stac", "api", "catalog", "spatiotemporal", "json", "cloud-native"]
    meta_region = "Global"
    meta_resolution = "Variable"
    meta_license = "Varies"
    meta_provides = ["file", "raster", "vector", "point_cloud", "archive"]
    meta_urls = {
        "spec": "https://stacspec.org/",
        "browser": "https://radiantearth.github.io/stac-browser/",
    }
    DEFAULT_API = "https://earth-search.aws.element84.com/v1"

    def __init__(
        self,
        url=None,
        collections=None,
        assets=None,
        asset_roles=None,
        asset_media_types=None,
        date=None,
        cloud_cover=None,
        query=None,
        filter=None,
        filter_lang=None,
        ids=None,
        sign="auto",
        data_type=None,
        limit=500,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_url = url or self.DEFAULT_API
        if urlsplit(self.api_url).scheme not in {"http", "https"}:
            raise ValueError("STAC URL must use HTTP(S)")

        self.collections = _list(collections)
        self.asset_keys = _list(assets)
        self.asset_roles = _list(asset_roles)
        self.asset_media_types = _list(asset_media_types)
        self.datetime = date
        self.cloud_cover = float(cloud_cover) if cloud_cover is not None else None
        if self.cloud_cover is not None and not (0 <= self.cloud_cover <= 100):
            raise ValueError("cloud_cover must be between 0 and 100")

        self.query = _mapping(query, "query")
        self.filter = (
            _mapping(filter, "filter")
            if isinstance(filter, (dict,))
            or (isinstance(filter, str) and filter.lstrip().startswith("{"))
            else filter
        )
        self.filter_lang = filter_lang
        self.ids = _list(ids)
        self.sign = str(sign).lower()
        if self.sign not in {"auto", "none", "planetary_computer", "s3"}:
            raise ValueError("sign must be auto, none, planetary_computer or s3")

        self.data_type = data_type
        self.limit = int(limit)
        if self.limit <= 0:
            raise ValueError("limit must be positive")

        if (
            self.cloud_cover is not None
            and self.query
            and "eo:cloud_cover" in self.query
        ):
            raise ValueError("cloud_cover conflicts with query.eo:cloud_cover")

        if self.asset_keys and "all" in self.asset_keys and len(self.asset_keys) > 1:
            raise ValueError("assets=all cannot be combined with other keys")

    def _query_region(self):
        # Base class may create a global fallback; omit bbox when -R was not supplied.
        if getattr(self, "_init_kwargs", {}).get("region") is None:
            return None

        return self.wgs_region

    def _open_catalog(self):
        return pystac_client.Client.open(self.api_url)

    def _build_search(self):
        params = {"max_items": self.limit}
        region = self._query_region()
        if region is not None:
            w, e, s, n = region
            params["bbox"] = (w, s, e, n)
        if self.collections:
            params["collections"] = self.collections
        if self.ids:
            params["ids"] = self.ids
        if self.datetime:
            params["datetime"] = self.datetime
        query = dict(self.query or {})
        if self.cloud_cover is not None:
            query["eo:cloud_cover"] = {"lt": self.cloud_cover}
        if query:
            params["query"] = query
        if self.filter is not None:
            params["filter"] = self.filter
        if self.filter_lang:
            params["filter_lang"] = self.filter_lang
        if region is None and not any(
            [
                self.collections,
                self.ids,
                self.datetime,
                self.query,
                self.filter,
                self.cloud_cover is not None,
            ]
        ):
            raise ValueError(
                "Unbounded STAC search requires collections, ids, date or a filter"
            )
        return params

    def _select_assets(self, item):
        available = item.assets
        if self.asset_keys:
            keys = list(available) if self.asset_keys == ["all"] else self.asset_keys
        elif self.asset_roles or self.asset_media_types:
            keys = list(available)
        else:
            keys = next(
                ([k] for k in ("visual", "data", "analytic") if k in available),
                list(available),
            )

        for key in keys:
            if key not in available:
                logger.debug("STAC item %s has no asset %s", item.id, key)
                continue

            asset = available[key]
            if self.asset_roles and not set(self.asset_roles).intersection(
                asset.roles or []
            ):
                continue

            media_type = (asset.media_type or "").split(";", 1)[0].lower()
            if self.asset_media_types and media_type not in [
                v.lower() for v in self.asset_media_types
            ]:
                continue

            yield key, asset

    def _resolve_asset_url(self, asset):
        href = asset.href
        mode = self.sign
        if mode == "auto":
            mode = (
                "planetary_computer"
                if "planetarycomputer.microsoft.com"
                in urlsplit(self.api_url).hostname.lower()
                else "s3"
                if href.startswith("s3://")
                else "none"
            )

        if mode == "planetary_computer":
            if planetary_computer is None:
                logger.warning(
                    "planetary-computer not installed; unsigned asset may fail"
                )
            else:
                href = planetary_computer.sign(href)
        elif mode == "s3" and href.startswith("s3://"):
            if boto3 is not None:
                try:
                    parts = urlsplit(href)
                    href = boto3.client("s3").generate_presigned_url(
                        "get_object",
                        Params={"Bucket": parts.netloc, "Key": parts.path.lstrip("/")},
                        ExpiresIn=3600,
                    )
                except Exception as exc:
                    logger.warning("Unable to presign S3 asset (%s), trying HTTPS", exc)
                    href = _s3_public_url(href)
            else:
                logger.warning(
                    "boto3 not installed; S3 HTTPS fallback may require public access"
                )
                href = _s3_public_url(href)

        if urlsplit(href).scheme not in {"http", "https"}:
            raise ValueError(f"Asset URL is not downloadable via HTTP(S): {href}")

        return href

    def _asset_to_entry(self, item, key, asset):
        href = self._resolve_asset_url(asset)
        date_str = item.datetime.strftime("%Y%m%d") if item.datetime else "nodate"
        ext = _extension(href, asset.media_type)
        dst_fn = (
            f"{_safe(item.collection_id)}_{date_str}_{_safe(item.id)}_{_safe(key)}{ext}"
        )
        metadata = {
            "stac_id": item.id,
            "stac_collection": item.collection_id,
            "stac_asset": key,
            "stac_datetime": item.datetime.isoformat() if item.datetime else None,
            "stac_bbox": item.bbox,
            "stac_media_type": asset.media_type,
            "stac_roles": list(asset.roles or []),
            "stac_properties": dict(item.properties or {}),
        }
        self.add_entry_to_results(
            url=href,
            dst_fn=dst_fn,
            data_type=self.data_type or _infer_type(ext, asset.media_type),
            metadata=metadata,
        )

    def run(self):
        self.results = []
        self._discovery_failed = False
        if pystac_client is None:
            self._discovery_failed = True
            self.status = -1
            logger.error("STAC requires pystac-client: pip install pystac-client")
            return self

        try:
            params = self._build_search()
            client = self._open_catalog()
            search = client.search(**params)
            count = 0
            for item in search.items():
                if count >= self.limit:
                    break
                count += 1
                for key, asset in self._select_assets(item):
                    self._asset_to_entry(item, key, asset)
        except Exception as exc:
            self._discovery_failed = True
            self.status = -1
            logger.exception("STAC discovery failed: %s", exc)
        return self


@cli.cli_opts(help_text="USGS 3DEP Seamless DEMs via Planetary Computer STAC")
class STAC_3DEP_Seamless(STACModule):
    name = "stac_3dep"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Seamless DEMs via STAC"
    meta_aliases = ["stac_ned", "pc_3dep"]

    def __init__(self, **kwargs):
        defaults = dict(
            url="https://planetarycomputer.microsoft.com/api/stac/v1",
            collections="3dep-seamless",
            assets="data",
            limit=1000,
        )
        super().__init__(**{**defaults, **kwargs})


@cli.cli_opts(help_text="USGS 3DEP Lidar COPC via Planetary Computer STAC")
class STAC_3DEP_Lidar(STACModule):
    name = "stac_lidar"
    meta_category = "Topography"
    meta_desc = "USGS 3DEP Lidar Point Clouds (COPC/LAZ) via STAC"
    meta_aliases = ["stac_laz", "pc_lidar"]

    def __init__(self, **kwargs):
        defaults = dict(
            url="https://planetarycomputer.microsoft.com/api/stac/v1",
            collections="3dep-lidar-copc",
            assets="data",
            limit=1000,
        )
        super().__init__(**{**defaults, **kwargs})
