#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generic THREDDS catalog discovery for Fetchez.

Discover datasets through THREDDS catalog.xml (including catalogRef and compound
services) or register an explicit NCSS/WCS dataset endpoint for subsetting.

Examples of THREDDS catalogs (check current availability):
  NOAA NCEI: https://www.ngdc.noaa.gov/thredds/catalog/regional/catalog.xml
  Unidata test: https://thredds.ucar.edu/thredds/catalog.xml

HTTPServer produces downloadable files. OPENDAP produces remote-access endpoints
and should be used with compatible readers, not an ordinary file downloader.
"""

import hashlib
import json
import logging
import re
from collections import deque
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from fetchez import core
from fetchez.cli import cli_opts
from fetchez.modules import FetchModule
from fetchez.spatial import Region

logger = logging.getLogger(__name__)
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _tag(node):
    return node.tag.rsplit("}", 1)[-1]


def _children(node, name):
    return [child for child in node if _tag(child) == name]


def _one(node, name):
    return next(iter(_children(node, name)), None)


def _list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x) for x in value]


def _mapping(value, label):
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping or JSON object")
    return value


def _origin(url):
    p = urlsplit(url)
    return (
        p.scheme.lower(),
        (p.hostname or "").lower(),
        p.port or (443 if p.scheme == "https" else 80),
    )


def _catalog_url(url):
    if url.endswith("/catalog.html"):
        return url[:-4] + "xml"
    if url.endswith("/catalog"):
        return url + ".xml"
    return url


def _service_map(root, catalog_url):
    """Map named services to concrete leaf service definitions.

    Compound services are not usable directly; child services inherit their
    base paths and are resolved by serviceType, not a vendor-specific name.
    """
    service_root = _one(root, "service")
    if service_root is None:
        return {}
    result = {}

    def descend(node, prefix=""):
        name = node.attrib.get("name")
        typ = node.attrib.get("serviceType", "").upper()
        base = node.attrib.get("base", "")
        if base.startswith(("http://", "https://")):
            absolute_base = base
        elif base.startswith("/"):
            p = urlsplit(catalog_url)
            absolute_base = f"{p.scheme}://{p.netloc}{base}"
        else:
            absolute_base = urljoin(prefix or catalog_url, base)
        if typ == "COMPOUND":
            leaves = []
            for child in _children(node, "service"):
                leaves.extend(descend(child, absolute_base))
        else:
            leaves = [(typ, absolute_base)] if typ else []
        if name:
            result[name] = leaves
        return leaves

    for service in _children(root, "service"):
        descend(service)
    return result


def _metadata_child(node, name):
    direct = _one(node, name)
    if direct is not None:
        return direct
    for metadata in _children(node, "metadata"):
        found = _one(metadata, name)
        if found is not None:
            return found
    return None


def _coverage(node):
    geo = _metadata_child(node, "geospatialCoverage")
    if geo is None:
        return None
    try:
        ns = _one(geo, "northsouth")
        ew = _one(geo, "eastwest")
        s = float(_one(ns, "start").text)
        dy = float(_one(ns, "size").text)
        w = float(_one(ew, "start").text)
        dx = float(_one(ew, "size").text)
        bounds = [min(w, w + dx), max(w, w + dx), min(s, s + dy), max(s, s + dy)]
        region = Region(*bounds, srs="EPSG:4326")
        return bounds if region.valid_p() else None
    except (AttributeError, TypeError, ValueError):
        return None


def _file_name(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return value[:180] or "dataset"


def _add_query(url, params):
    parts = urlsplit(url)
    existing = parse_qsl(parts.query, keep_blank_values=True)
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        existing.append((k, v))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(existing, doseq=True),
            parts.fragment,
        )
    )


def _make_subset(service, url, params, region):
    """Construct a query for NCSS Grid or WCS GetCoverage."""
    service = service.upper()
    q = dict(params)
    if service == "NCSS":
        if region is not None:
            w, e, s, n = region
            for k, v in {"west": w, "east": e, "south": s, "north": n}.items():
                q.setdefault(k, v)
        q.setdefault("accept", "netcdf")
    elif service == "WCS":
        q.setdefault("service", "WCS")
        q.setdefault("version", "1.0.0")
        q.setdefault("request", "GetCoverage")
        if region is not None:
            w, e, s, n = region
            q.setdefault("bbox", f"{w},{s},{e},{n}")
        q.setdefault("format", "geotiff_float")
    return _add_query(url, q)


@cli_opts(
    help_text="Discover THREDDS datasets or request NCSS/WCS subsets.",
    url="THREDDS catalog.xml URL, or direct NCSS/WCS dataset endpoint.",
    catalog_url="Alias for url (catalog XML).",
    service="HTTPServer (default), OPENDAP, NCSS, or WCS.",
    pattern="Dataset name glob(s), e.g. *.nc, or substring(s).",
    recursive="Follow THREDDS catalogRef links (default true).",
    max_depth="Maximum catalogRef traversal depth.",
    max_catalogs="Maximum number of catalog XML requests.",
    limit="Maximum number of registered dataset entries.",
    spatial="known (default), strict, or none: how missing bounds are treated.",
    parameters="NCSS/WCS query parameters (YAML dict or JSON object).",
    dataset="Optional dataset name/id substring filter.",
)
class THREDDS(FetchModule):
    name = "thredds"
    meta_category = "Generic"
    meta_desc = "THREDDS XML catalog discovery and NCSS/WCS data access"
    meta_tags = ["thredds", "netcdf", "opendap", "oceanography", "catalog", "ncss"]
    meta_provides = ["file", "netcdf", "raster", "timeseries"]
    meta_resolution = "varies"
    meta_license = "varies"

    SERVICE_ALIASES = {
        "HTTP": "HTTPSERVER",
        "HTTPSERVER": "HTTPSERVER",
        "OPENDAP": "OPENDAP",
        "DAP": "OPENDAP",
        "DODS": "OPENDAP",
        "NCSS": "NCSS",
        "NCSSGRID": "NCSS",
        "NETCDFSUBSET": "NCSS",
        "WCS": "WCS",
    }

    def __init__(
        self,
        url=None,
        catalog_url=None,
        service="HTTPServer",
        pattern=None,
        dataset=None,
        recursive=True,
        max_depth=5,
        max_catalogs=200,
        limit=500,
        spatial="known",
        parameters=None,
        data_type=None,
        metadata=None,
        allow_cross_origin=False,
        iso_fallback=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.url = _catalog_url(url or catalog_url or "")
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("url or catalog_url must be an HTTP(S) URL")
        self.service = self.SERVICE_ALIASES.get(service.upper())
        if self.service is None:
            raise ValueError("service must be HTTPServer, OPENDAP, NCSS, or WCS")
        self.pattern = _list(pattern)
        self.dataset = dataset
        self.recursive = bool(recursive)
        self.max_depth = int(max_depth)
        self.max_catalogs = int(max_catalogs)
        self.limit = int(limit)
        self.spatial = spatial.lower()
        self.parameters = _mapping(parameters, "parameters")
        self.data_type = data_type
        self.entry_metadata = _mapping(metadata, "metadata")
        self.allow_cross_origin = bool(allow_cross_origin)
        self.iso_fallback = bool(iso_fallback)
        if self.spatial not in ("known", "strict", "none"):
            raise ValueError("spatial must be known, strict, or none")
        if self.max_depth < 0 or self.max_catalogs < 1 or self.limit < 1:
            raise ValueError("invalid crawl bounds or limit")

    def _region(self):
        init = getattr(self, "_init_kwargs", {})
        return self.wgs_region if init.get("region") is not None else None

    def _match(self, name, identity=""):
        if self.dataset and self.dataset.lower() not in f"{name} {identity}".lower():
            return False
        if self.pattern and not any(
            fnmatch(name.lower(), p.lower()) or p.lower() in name.lower()
            for p in self.pattern
        ):
            return False
        return True

    def _iso_bounds(self, url):
        if not self.iso_fallback or not url:
            return None
        try:
            from shapely.geometry import shape

            doc = core.iso_xml(url)
            geom = doc.polygon(geom=True) if doc.xml_doc is not None else None
            if geom:
                return shape(geom).bounds  # minx, miny, maxx, maxy
        except Exception as exc:
            logger.debug("Could not parse ISO footprint %s: %s", url, exc)
        return None

    def _include(self, bounds, region, iso_url=None):
        if region is None or self.spatial == "none":
            return True
        if bounds is None and iso_url:
            bbox = self._iso_bounds(iso_url)
            if bbox:
                bounds = [bbox[0], bbox[2], bbox[1], bbox[3]]
        if bounds is None:
            return self.spatial == "known"
        try:
            w, e, s, n = bounds
            # Independent bbox comparison, no Shapely needed for catalog scanning.
            rw, re, rs, rn = region
            return not (e < rw or re < w or n < rs or rn < s)
        except (ValueError, TypeError):
            return self.spatial == "known"

    def _emit(self, href, name, identity, bounds, service, region):
        if len(self.results) >= self.limit:
            return
        download_url = (
            _make_subset(service, href, self.parameters, region)
            if service in ("NCSS", "WCS")
            else href
        )
        suffix = (
            ".tif"
            if service == "WCS"
            else ".nc"
            if service == "NCSS"
            else Path(urlsplit(href).path).suffix
        )
        base = _file_name(name or identity or Path(urlsplit(href).path).name)
        if suffix and not base.lower().endswith(suffix.lower()):
            base = f"{Path(base).stem}{suffix}"
        if service in ("NCSS", "WCS"):
            digest = hashlib.sha256(download_url.encode("utf-8")).hexdigest()[:10]
            base = f"{Path(base).stem}_{digest}{Path(base).suffix}"

        dtype = self.data_type or (
            "raster"
            if service == "WCS"
            else "netcdf"
            if service in ("NCSS", "HTTPSERVER") and base.lower().endswith(".nc")
            else "opendap"
            if service == "OPENDAP"
            else "file"
        )
        props = dict(self.entry_metadata)
        props.update({"thredds_id": identity, "thredds_service": service})
        if bounds is not None:
            props["thredds_bounds"] = bounds
        self.add_entry_to_results(
            url=download_url, dst_fn=base, data_type=dtype, metadata=props
        )

    def _scan_catalog(self, catalog_url, region):
        queue = deque([(catalog_url, 0)])
        visited = set()
        seen_assets = set()
        while queue and len(self.results) < self.limit:
            page_url, depth = queue.popleft()
            if page_url in visited:
                continue
            if len(visited) >= self.max_catalogs:
                raise RuntimeError("THREDDS catalog traversal exceeded max_catalogs")
            if not self.allow_cross_origin and _origin(page_url) != _origin(self.url):
                logger.warning("Skipping cross-origin catalogRef: %s", page_url)
                continue
            visited.add(page_url)
            root = core.Fetch(page_url).fetch_xml()
            if root is None:
                raise RuntimeError(f"Could not retrieve THREDDS XML catalog {page_url}")
            services = _service_map(root, page_url)

            def scan_dataset(
                node,
                services,
                inherited_service=None,
                inherited_bounds=None,
            ):
                service_name = node.attrib.get("serviceName", inherited_service)
                service_node = _metadata_child(node, "serviceName")
                if service_node is not None and service_node.text:
                    service_name = service_node.text.strip()
                bounds = _coverage(node) or inherited_bounds
                name = node.attrib.get("name", "")
                identity = node.attrib.get("ID", "")
                url_path = node.attrib.get("urlPath")
                accesses = [(url_path, service_name)] if url_path else []
                accesses.extend(
                    (a.attrib.get("urlPath"), a.attrib.get("serviceName", service_name))
                    for a in _children(node, "access")
                )
                if accesses and self._match(name, identity):
                    for path, svc in accesses:
                        if not path:
                            continue
                        service_entries = services.get(svc, [])
                        for typ, base in service_entries:
                            mapped_type = self.SERVICE_ALIASES.get(typ, typ)

                            if mapped_type != self.service:
                                continue

                            href = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
                            if href in seen_assets:
                                continue
                            iso = None

                            for typ, base in service_entries:
                                if typ == "ISO":
                                    iso = urljoin(
                                        base.rstrip("/") + "/",
                                        path.lstrip("/"),
                                    )
                                    break
                            if not self._include(bounds, region, iso):
                                continue
                            seen_assets.add(href)
                            self._emit(
                                href,
                                name or Path(path).name,
                                identity,
                                bounds,
                                mapped_type,
                                region,
                            )
                for child in _children(node, "dataset"):
                    scan_dataset(child, services, service_name, bounds)

            for ds in _children(root, "dataset"):
                scan_dataset(ds, services)
            if self.recursive and depth < self.max_depth:
                # catalogRef can appear under datasets as well as at root.
                for ref in root.iter():
                    if _tag(ref) != "catalogRef":
                        continue
                    href = ref.attrib.get(XLINK_HREF) or ref.attrib.get("href")
                    if href:
                        target = _catalog_url(urljoin(page_url, href))
                        if target not in visited:
                            queue.append((target, depth + 1))

    def run(self):
        self.results = []
        self._discovery_failed = False
        try:
            region = self._region()
            if "/catalog" in urlsplit(self.url).path or self.url.endswith(".xml"):
                self._scan_catalog(self.url, region)
            else:
                # Direct NCSS/WCS data endpoint, useful for stable known datasets.
                if self.service not in ("NCSS", "WCS"):
                    raise ValueError(
                        "Direct dataset URL requires service=NCSS or service=WCS"
                    )
                if region is None:
                    raise ValueError(
                        "Direct NCSS/WCS subsetting requires an explicit region"
                    )
                self._emit(
                    self.url,
                    Path(urlsplit(self.url).path).name,
                    self.url,
                    None,
                    self.service,
                    region,
                )
        except Exception as exc:
            self._discovery_failed = True
            self.status = -1
            logger.exception("THREDDS discovery failed: %s", exc)
        return self
