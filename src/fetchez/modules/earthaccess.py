#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.modules.earthaccess
~~~~~~~~~~~~~~~~~~~~~~~~~~~

NASA CMR discovery and provider-aware acquisition through earthaccess.

Discovery creates serializable entries without downloading. ``fetch_entry``
uses an earthaccess-authorized HTTPS session for external links. Direct/cloud
links are discoverable but deliberately not acquired until remote access is
supported by the Fetchez reader contract.

The original short_name/concept_id/version interface remains supported.
``resource='collections'`` provides metadata-only collection discovery through
``self.collections``; it deliberately creates no downloadable entries.
"""

from __future__ import annotations

import datetime as _datetime
import fnmatch
import hashlib
import logging
import os
import posixpath
import re
import tempfile
from pathlib import Path
from tqdm.auto import tqdm

import filelock
import requests

from fetchez.core import FetchCancelled, FetchError
from urllib.parse import unquote, urlsplit

from fetchez import cli
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

# Allow specific additional CMR search keys, never arbitrary Fetchez base args.
_EXTRA_SEARCH_KEYS = frozenset(
    {
        "doi",
        "daac",
        "data_center",
        "provider",
        "provider_id",
        "cloud_hosted",
        "downloadable",
        "online_only",
        "orbit_number",
        "granule_name",
        "instrument",
        "platform",
        "day_night_flag",
        "entry_title",
        "keyword",
        "native_id",
    }
)
# Browsing and service links should not accidentally become data downloads.
_BROWSE_SUFFIXES = (".xml", ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".iso", ".html")
_FORMAT_TYPES = {
    ".tif": "raster",
    ".tiff": "raster",
    ".cog": "raster",
    ".nc": "file",
    ".nc4": "file",
    ".h5": "file",
    ".hdf": "file",
    ".hdf5": "file",
    ".zarr": "file",
    ".zip": "archive",
    ".csv": "csv",
    ".json": "json",
    ".geojson": "vector",
    ".gpkg": "vector",
    ".parquet": "file",
    ".laz": "file",
    ".las": "file",
}


def _plain(value):
    """Convert CMR metadata to durable JSON-compatible primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (_datetime.date, _datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    # Do not stringify opaque objects into metadata (may include credentials).
    return None


def _record_dict(record):
    if isinstance(record, dict):
        return record
    # earthaccess DataGranule implements mapping-like access in supported releases.
    try:
        return dict(record)
    except (TypeError, ValueError):
        return {}


def _record_meta(record):
    raw = _record_dict(record)
    return _plain(raw.get("meta") or {}), _plain(raw.get("umm") or {})


def _record_id(meta, umm):
    return (
        meta.get("concept-id") or umm.get("GranuleUR") or umm.get("EntryTitle") or None
    )


def _filename(url):
    path = unquote(urlsplit(url).path.rstrip("/"))
    name = posixpath.basename(path)
    return name or "earthaccess-" + hashlib.sha256(url.encode()).hexdigest()[:12]


def _data_type(url):
    name = urlsplit(url).path.lower()
    for suffix, data_type in _FORMAT_TYPES.items():
        if name.endswith(suffix):
            return data_type
    return "file"


def _parse_pair(value, name, caster=str):
    if value is None:
        return None
    if isinstance(value, str):
        value = re.split(r"\s*[,/]\s*", value.strip())
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a pair")
    return tuple(caster(v) for v in value)


def _unique_filename(name, granule_id, used):
    """Avoid overwriting different assets with identical basenames."""
    if name not in used:
        used.add(name)
        return name
    stem, ext = os.path.splitext(name)
    digest = hashlib.sha256(str(granule_id).encode()).hexdigest()[:10]
    candidate = f"{stem}_{digest}{ext}"
    n = 2
    while candidate in used:
        candidate = f"{stem}_{digest}_{n}{ext}"
        n += 1
    used.add(candidate)
    return candidate


@cli.cli_opts(
    help_text="NASA Earth science discovery via the earthaccess Python library",
    resource="Search resource: granules (default) or collections (metadata-only)",
    short_name="CMR dataset short name, e.g. ATL03",
    concept_id="CMR collection/granule concept ID",
    version="Dataset version, e.g. 006",
    count="Maximum number of search results (-1 for all)",
    temporal="Search period as start,end ISO dates",
    cloud_cover="Cloud cover min,max range",
    provider="CMR provider ID",
    cloud_hosted="Limit search to Earthdata Cloud hosted collections",
    access="Granule link access: external (HTTPS) or direct (cloud)",
    links="Asset selection: first or all",
    link_pattern="Optional glob pattern for asset filename/URL",
    auth="Authentication: none, auto, netrc, environment, interactive",
)
class EarthAccess(FetchModule):
    """Expose earthaccess CMR searches as standard Fetchez file entries.

    ``search_kwargs`` accepts supported optional CMR filters; collection
    metadata discovery is available via ``resource='collections'`` and
    ``self.collections`` (no placeholder download entries).

    ``auth='auto'`` attempts environment credentials, then netrc, without an
    interactive fallback. This makes automated recipes safe from surprise
    credential prompts. CMR searches generally do not require authentication.

    ``access='direct'`` discovers cloud links, but ``fetch_entry`` currently
    supports HTTPS/HTTP only; direct acquisition needs future reader support.
    """

    name = "earthaccess"
    meta_category = "Generic"
    meta_desc = "NASA CMR collection and granule discovery using earthaccess"
    meta_agency = "NASA"
    meta_tags = ["nasa", "cmr", "earthaccess", "satellite", "remote-sensing", "cloud"]
    meta_region = "Global"
    meta_resolution = "Varies"
    meta_license = "Per-collection NASA data distribution policy"
    meta_urls = {
        "home": "https://www.earthdata.nasa.gov/",
        "search": "https://search.earthdata.nasa.gov/",
        "git": "https://github.com/earthaccess-dev/earthaccess",
    }
    meta_provides = ["file", "raster", "archive", "vector", "csv", "json"]

    def __init__(
        self,
        short_name=None,
        concept_id=None,
        version=None,
        resource="granules",
        count=-1,
        limit=None,
        temporal=None,
        cloud_cover=None,
        polygon=None,
        point=None,
        provider=None,
        cloud_hosted=None,
        downloadable=None,
        granule_name=None,
        access="external",
        links="first",
        link_pattern=None,
        include_browse=False,
        auth="none",
        search_kwargs=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.short_name = short_name
        self.concept_id = concept_id
        self.version = version
        self.resource = str(resource).lower()
        self.count = int(limit if limit is not None else count)
        self.temporal = _parse_pair(temporal, "temporal")
        self.cloud_cover = _parse_pair(cloud_cover, "cloud_cover", float)
        self.polygon = polygon
        self.point = point
        self.provider = provider
        self.cloud_hosted = cloud_hosted
        self.downloadable = downloadable
        self.granule_name = granule_name
        self.access = str(access).lower()
        self.links = str(links).lower()
        self.link_pattern = link_pattern
        self.include_browse = include_browse
        self.auth = str(auth).lower()
        self.search_kwargs = dict(search_kwargs or {})
        self.collections = []
        self.tags = ["nasa", "earthdata", "earthaccess", "cmr"]
        if short_name:
            self.tags.append(str(short_name).lower())
        if self.resource not in {"granules", "collections"}:
            raise ValueError("resource must be granules or collections")
        if self.access not in {"external", "direct"}:
            raise ValueError("access must be external or direct")
        if self.links not in {"first", "all"}:
            raise ValueError("links must be first or all")
        if self.auth not in {"none", "auto", "netrc", "environment", "interactive"}:
            raise ValueError("unknown auth strategy")
        if self.count < -1:
            raise ValueError("count must be -1 or nonnegative")
        unknown = set(self.search_kwargs).difference(_EXTRA_SEARCH_KEYS)
        if unknown:
            raise ValueError(f"Unsupported search_kwargs: {sorted(unknown)}")

    def _authenticate(self, earthaccess):
        if self.auth == "none":
            return
        strategies = ("environment", "netrc") if self.auth == "auto" else (self.auth,)
        last_error = None
        for strategy in strategies:
            try:
                result = earthaccess.login(strategy=strategy)
                if getattr(result, "authenticated", False):
                    return
                last_error = RuntimeError(f"{strategy} authentication unsuccessful")
            except Exception as exc:
                last_error = exc
                logger.debug(
                    "earthaccess authentication failed using %s: %s", strategy, exc
                )
        raise RuntimeError(
            "Earthdata authentication failed; check selected strategy"
        ) from last_error

    def _query(self):
        query = {}
        if self.short_name:
            query["short_name"] = self.short_name
        if self.concept_id:
            query["concept_id"] = self.concept_id
        if self.version:
            query["version"] = self.version
        for key in ("provider", "cloud_hosted", "downloadable", "granule_name"):
            value = getattr(self, key)
            if value is not None:
                query[key] = value
        if self.cloud_cover is not None:
            query["cloud_cover"] = self.cloud_cover
        if self.temporal is not None:
            query["temporal"] = self.temporal
        elif self.min_year or self.max_year:
            start = f"{self.min_year}-01-01" if self.min_year else "1900-01-01"
            end = (
                f"{self.max_year}-12-31"
                if self.max_year
                else _datetime.datetime.now(_datetime.timezone.utc).strftime("%Y-%m-%d")
            )
            query["temporal"] = (start, end)
        if self.polygon is not None:
            query["polygon"] = self.polygon
        elif self.point is not None:
            query["point"] = self.point
        elif self.wgs_region:
            west, east, south, north = self.wgs_region
            query["bounding_box"] = (west, south, east, north)
        # Constructor options win over supplemental search kwargs.
        for key, value in self.search_kwargs.items():
            if key in query:
                raise ValueError(f"Duplicate CMR filter {key!r}")
            query[key] = value
        if not any(
            k in query
            for k in (
                "short_name",
                "concept_id",
                "provider",
                "provider_id",
                "version",
                "entry_title",
                "doi",
            )
        ):
            if self.resource == "granules":
                raise ValueError(
                    "CMR granule searches require a dataset/provider selector"
                )
        return query

    def _links_for_granule(self, granule):
        urls = granule.data_links(access=self.access)
        if urls is None:
            return []
        selected = []
        for link in urls:
            if not isinstance(link, str):
                continue
            path = urlsplit(link).path.lower()
            if not self.include_browse and path.endswith(_BROWSE_SUFFIXES):
                continue
            if self.link_pattern and not (
                fnmatch.fnmatch(_filename(link), self.link_pattern)
                or fnmatch.fnmatch(link, self.link_pattern)
            ):
                continue
            if link not in selected:
                selected.append(link)
        return selected[:1] if self.links == "first" else selected

    def run(self):
        try:
            import earthaccess
        except ImportError:
            logger.error("Module 'earthaccess' requires: pip install earthaccess")
            raise

        self._authenticate(earthaccess)
        query = self._query()
        logger.info("earthaccess: searching %s with %s", self.resource, query)
        # Do not reassign results: base class may own/reset it for discovery cache.
        if self.resource == "collections":
            found = earthaccess.search_datasets(count=self.count, **query)
            self.collections = [_plain(_record_dict(rec)) for rec in found]
            logger.info(
                "earthaccess: found %s collections (metadata only)",
                len(self.collections),
            )
            return self

        granules = earthaccess.search_data(count=self.count, **query)
        logger.info("earthaccess: found %s granules", len(granules))
        used_names = {
            Path(str(entry.get("dst_fn"))).name
            for entry in self.results
            if isinstance(entry, dict) and entry.get("dst_fn")
        }
        for granule in granules:
            meta, umm = _record_meta(granule)
            granule_id = _record_id(meta, umm)
            for url in self._links_for_granule(granule):
                name = _unique_filename(_filename(url), granule_id or url, used_names)
                self.add_entry_to_results(
                    url=url,
                    dst_fn=name,
                    data_type=_data_type(url),
                    metadata={
                        "earthaccess": {
                            "granule_id": granule_id,
                            "collection_id": meta.get("collection-concept-id"),
                            "provider": meta.get("provider-id") or self.provider,
                            "native_meta": meta,
                            "native_umm": umm,
                            "access": self.access,
                            "url": url,
                        },
                    },
                )
        return self

    def fetch_entry(self, entry, check_size=True, retries=5, verbose=True):
        """Materialize one external CMR asset using Earthdata-aware HTTP access.

        The entry's URL and metadata are sufficient to replay this operation
        after discovery caching. No granule object or stored credentials needed.
        """
        try:
            import earthaccess
        except ImportError:
            logger.error("Module 'earthaccess' requires: pip install earthaccess")
            raise

        url = entry["url"]
        access = (
            entry.get("metadata", {}).get("earthaccess", {}).get("access", self.access)
        )
        if access != "external" or urlsplit(url).scheme not in {"http", "https"}:
            raise FetchError(
                "earthaccess fetch_entry currently supports external HTTP(S) links only; "
                "use access='external' for local acquisition"
            )

        output = Path(entry["dst_fn"])
        output.parent.mkdir(parents=True, exist_ok=True)
        execution = self.context

        def check_cancelled():
            if execution is not None and execution.cancelled:
                raise FetchCancelled("Earthaccess acquisition cancelled")

        check_cancelled()
        # The earthaccess client handles EDL cookies and authorized redirects.
        # 'none' retains unauthenticated access for openly hosted assets.
        # A private temp file prevents incomplete outputs being treated as cached
        # successes. Per-path locks also protect concurrent Fetchez workers.
        with filelock.FileLock(f"{output}.lock", timeout=3600):
            check_cancelled()
            if output.is_file() and (not check_size or output.stat().st_size > 0):
                entry["status"] = 0
                return 0

            if self.auth != "none":
                self._authenticate(earthaccess)
                session = earthaccess.get_requests_https_session()
            else:
                session = requests.Session()

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=output.parent,
                    prefix=f".{output.name}.",
                    suffix=".part",
                    delete=False,
                ) as tmp:
                    tmp_path = Path(tmp.name)
                    with session.get(url, stream=True, timeout=(30, 120)) as response:
                        response.raise_for_status()

                        total = int(response.headers.get("Content-Length", 0))

                        with tqdm(
                            total=total if total > 0 else None,
                            desc=Path(entry["dst_fn"]).name,
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                            disable=not verbose or self.silent,
                            leave=False,
                        ) as progress:
                            for chunk in response.iter_content(chunk_size=1024 * 1024):
                                check_cancelled()
                                if chunk:
                                    tmp.write(chunk)
                                    progress.update(len(chunk))
                check_cancelled()
                if check_size and tmp_path.stat().st_size == 0:
                    raise FetchError(f"Empty Earthdata download: {url}")
                tmp_path.replace(output)
                tmp_path = None
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)
                session.close()

        entry["status"] = 0
        return 0
