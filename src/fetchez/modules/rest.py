#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generic, declarative REST discovery module for Fetchez.

Modes:
  response: register a GET response as a normal downloadable entry; for POST,
            materialize the response as a local artifact.
  discover: query JSON, select records, and register their asset URLs.

Spatial placeholders use Region.format(), e.g. ``{region:bbox}`` or
``{region:wkt}``. When a placeholder occupies an entire JSON value,
``{region:geojson}`` and ``{region:arcgis}`` produce native dictionaries.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, unquote
from urllib.request import Request, urlopen

from fetchez.cli import cli_opts
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"\{region(?::([a-zA-Z0-9_]+))?\}")
_FULL_TOKEN = re.compile(r"^\{region(?::([a-zA-Z0-9_]+))?\}$")
_MISSING = object()


def _mapping(value, label):
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dictionary or JSON object")
    return value


def _get_path(data, path, default=_MISSING):
    """Read dot-delimited keys and numeric indices, without evaluating expressions."""
    if path in (None, "", "."):
        return data
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif (
            isinstance(current, (list, tuple))
            and part.isdecimal()
            and int(part) < len(current)
        ):
            current = current[int(part)]
        else:
            if default is not _MISSING:
                return default
            raise KeyError(f"Path {path!r} not found at {part!r}")
    return current


def _safe_filename(value, fallback="resource"):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return text[:180] or fallback


def _query_pairs(value):
    """Preserve duplicate query keys, including ScienceBase-style filters."""
    if isinstance(value, dict):
        result = []
        for k, v in value.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                result.extend((k, item) for item in v)
            else:
                result.append((k, v))
        return result
    if isinstance(value, (list, tuple)):
        if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in value):
            raise ValueError("parameters list must contain [key, value] pairs")
        return [tuple(pair) for pair in value]
    raise ValueError("parameters must be a mapping or list of [key,value] pairs")


def _same_origin(url_a, url_b):
    """Compare HTTP origins, accounting for default ports."""

    def origin(url):
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        port = parts.port or (443 if scheme == "https" else 80)
        return scheme, parts.hostname, port

    return origin(url_a) == origin(url_b)


@cli_opts(
    help_text="Generic REST API response fetcher and JSON resource discovery.",
    url="API endpoint URL.",
    method="GET or POST.",
    parameters="JSON object or list of key/value pairs (repeated keys supported).",
    headers="JSON headers mapping (avoid embedding permanent secrets in YAML).",
    body="JSON body for POST (supports region placeholders).",
    mode="response (compatible default) or discover.",
    results_path="Dot path to JSON result array, e.g. features or data.items.",
    url_field="Dot path to asset URL within each record.",
    filename_field="Optional dot path to destination filename.",
    id_field="Optional dot path to stable record identifier.",
    metadata_fields="Optional mapping of metadata names to dot paths.",
    data_type="Entry type label (default file).",
    pagination="JSON pagination options: type=next|offset|page.",
    detail="Optional mapping for secondary detail requests per discovered item.",
    limit="Maximum number of discovered entries.",
)
class RestAPIModule(FetchModule):
    name = "rest_api"
    meta_category = "Generic"
    meta_desc = "Generic REST API response and JSON resource discovery"
    meta_tags = ["rest", "api", "json", "geojson", "etl"]
    meta_provides = ["file", "json", "raster", "vector", "archive"]
    meta_resolution = "Varies"
    meta_license = "Varies"

    def __init__(
        self,
        url=None,
        method="GET",
        headers=None,
        parameters=None,
        body=None,
        mode="response",
        results_path=None,
        url_field=None,
        filename_field=None,
        id_field=None,
        metadata_fields=None,
        detail=None,
        data_type="file",
        pagination=None,
        limit=500,
        out_ext=".json",
        timeout=30,
        region_srs="EPSG:4326",
        **kwargs,
    ):
        # Do not force name=...: FetchModule already has a class-level name.
        super().__init__(**kwargs)
        self.url = url
        self.method = method.upper()
        if self.method not in {"GET", "POST"}:
            raise ValueError("REST method must be GET or POST")
        if mode not in {"response", "discover"}:
            raise ValueError("mode must be response or discover")
        self.mode = mode
        self.req_headers = _mapping(headers, "headers")
        # Also set this on cached discoveries: _cached_run may skip run().
        self.headers.update(self.req_headers)
        if isinstance(parameters, str):
            parameters = json.loads(parameters)
        self.req_parameters = parameters if parameters is not None else {}
        self.body = json.loads(body) if isinstance(body, str) else body
        self.results_path = results_path
        self.url_field = url_field
        self.filename_field = filename_field
        self.id_field = id_field
        self.metadata_fields = _mapping(metadata_fields, "metadata_fields")
        self.detail = _mapping(detail, "detail")
        self.data_type = data_type
        self.pagination = _mapping(pagination, "pagination")
        self.limit = int(limit)
        self.timeout = float(timeout)
        self.region_srs = region_srs
        self.out_ext = out_ext if str(out_ext).startswith(".") else f".{out_ext}"
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.mode == "discover" and not self.url_field and not self.detail:
            raise ValueError("url_field is required in discover mode")

    def _region(self):
        """Return a copy of the query region in the requested CRS."""

        if self._init_kwargs.get("region") is None:
            raise ValueError("Region placeholder requires an explicit region")

        region = self.wgs_region.copy()

        if not region.valid_p():
            raise ValueError("Region placeholder requires valid bounds")

        if self.region_srs:
            region.warp(self.region_srs)

        return region

    def _region_value(self, style, native=False):
        region = self._region()
        style = style or "bbox"
        if native:
            if style == "geojson":
                return region.to_geojson_geometry()
            if style == "arcgis":
                return region.to_arcgis_envelope()
        return region.format(style)

    def _expand(self, obj):
        if isinstance(obj, str):
            match = _FULL_TOKEN.fullmatch(obj)
            if match:
                return self._region_value(match.group(1), native=True)
            return _TOKEN.sub(lambda m: str(self._region_value(m.group(1))), obj)
        if isinstance(obj, dict):
            return {k: self._expand(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._expand(v) for v in obj]
        return obj

    def _build_url(self, url, parameters):
        parts = urlsplit(url)
        pairs = parse_qsl(parts.query, keep_blank_values=True) + _query_pairs(
            parameters
        )
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(pairs, doseq=True),
                parts.fragment,
            )
        )

    def build_url(self):
        """Public compatibility helper for GET-style module configurations."""
        return self._build_url(
            self._expand(self.url), self._expand(self.req_parameters)
        )

    def _request(self, url, parameters, body=None, method=None, headers=None):
        method = (method or self.method).upper()
        request_url = self._build_url(url, parameters)

        if headers is None:
            headers = dict(self.req_headers)

        payload = None
        if method == "POST" and body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        request = Request(
            request_url,
            data=payload,
            headers=headers,
            method=method,
        )

        with urlopen(request, timeout=self.timeout) as response:
            return response.read(), response.geturl()

    # def _request(self, url, parameters, body=None, method=None):
    #     method = (method or self.method).upper()
    #     request_url = self._build_url(url, parameters)
    #     payload = None
    #     headers = dict(self.req_headers)
    #     if self.method == "POST" and body is not None:
    #         payload = json.dumps(body).encode("utf-8")
    #         headers.setdefault("Content-Type", "application/json")

    #     request = Request(request_url, data=payload, headers=headers, method=self.method)
    #     with urlopen(request, timeout=self.timeout) as response:
    #         return response.read(), response.geturl()

    def _records(self, response):
        result = _get_path(response, self.results_path)
        if isinstance(result, dict):
            result = [result]

        if not isinstance(result, list):
            raise ValueError("results_path must point to a JSON object or array")

        return result

    def _fetch_detail(self, record, base_url):
        """Perform a secondary request to fetch detailed asset information."""
        href = _get_path(record, self.detail.get("url_field"), default=None)
        if not isinstance(href, str) or not href.strip():
            logger.debug(
                "Skipping record without detail URL at %r", self.detail.get("url_field")
            )
            return

        href = urljoin(base_url, href)

        if urlsplit(href).scheme not in {"http", "https"}:
            raise ValueError("Discovered asset URL must use HTTP(S)")

        if _same_origin(href, base_url):
            headers = dict(self.req_headers)
        else:
            headers = {}

        parameters = self._expand(self.detail.get("parameters", {}))

        try:
            content, final_url = self._request(
                href,
                self._expand(parameters),
                method=self.detail.get("method", "GET"),
                headers=headers,
            )
            detail_data = json.loads(content)
        except Exception as exc:
            self._discovery_failed = True
            logger.warning("Detail request failed for %s: %s", href, exc)
            return

        items = _get_path(
            detail_data, self.detail.get("results_path"), default=detail_data
        )
        if isinstance(items, dict):
            items = [items]

        if not isinstance(items, list):
            items = []

        parent_id = (
            _get_path(record, self.id_field, default=None) if self.id_field else None
        )
        parent_meta = {
            key: _get_path(record, path, default=None)
            for key, path in self.metadata_fields.items()
        }

        if parent_id is not None:
            parent_meta["source_id"] = parent_id

        asset_url_field = self.detail.get("asset_url_field")
        filename_field = self.detail.get("filename_field")
        detail_meta_fields = self.detail.get("metadata_fields", {})

        for item in items:
            asset_href = _get_path(item, asset_url_field, default=None)
            if not isinstance(asset_href, str) or not asset_href.strip():
                self._discovery_failed = True
                continue

            asset_href = urljoin(final_url, asset_href)
            if urlsplit(asset_href).scheme not in {"http", "https"}:
                continue

            suggested_name = (
                _get_path(item, filename_field, default=None)
                if filename_field
                else None
            )
            filename = (
                _safe_filename(suggested_name)
                if suggested_name
                else _safe_filename(
                    unquote(Path(urlsplit(asset_href).path).name), "resource"
                )
            )

            digest = hashlib.sha256(asset_href.encode("utf-8")).hexdigest()[:12]
            stem, ext = Path(filename).stem, Path(filename).suffix
            filename = f"{stem}_{digest}{ext}"

            metadata = dict(parent_meta)
            metadata.update(
                {
                    key: _get_path(item, path, default=None)
                    for key, path in detail_meta_fields.items()
                }
            )

            yield asset_href, filename, metadata

    def _entry_from_record(self, record, base_url):
        href = _get_path(record, self.url_field, default=None)
        if not isinstance(href, str) or not href.strip():
            logger.debug("Skipping record without URL at %r", self.url_field)
            return None

        href = urljoin(base_url, href)
        if urlsplit(href).scheme not in {"http", "https"}:
            raise ValueError("Discovered asset URL must use HTTP(S)")

        record_id = (
            _get_path(record, self.id_field, default=None) if self.id_field else None
        )
        suggested_name = (
            _get_path(record, self.filename_field, default=None)
            if self.filename_field
            else None
        )
        filename = (
            _safe_filename(suggested_name)
            if suggested_name
            else _safe_filename(unquote(Path(urlsplit(href).path).name), "resource")
        )

        # Keep original extension if it exists; stable suffix avoids collisions.
        digest = hashlib.sha256(href.encode("utf-8")).hexdigest()[:12]
        stem, ext = Path(filename).stem, Path(filename).suffix
        filename = f"{stem}_{digest}{ext}"
        metadata = {
            key: _get_path(record, path, default=None)
            for key, path in self.metadata_fields.items()
        }

        if record_id is not None:
            metadata["source_id"] = record_id

        return href, filename, metadata

    def _next(self, response, current_url, parameters, page, records_count):
        config = self.pagination
        kind = config.get("type")
        if not kind:
            return None
        if kind == "next":
            target = _get_path(response, config.get("path", "next"), default=None)
            if not target:
                return None
            if isinstance(target, dict):
                target = target.get("href")
            if not isinstance(target, str) or not target:
                return None
            # Link becomes full next request; do not reapply old parameters.
            next_url = urljoin(current_url, target)
            # Do not forward credentials to an arbitrary host supplied by the API.
            if urlsplit(next_url).netloc != urlsplit(current_url).netloc:
                raise ValueError("Cross-host pagination link refused")
            return next_url, {}
        page_size = int(config.get("page_size", 100))
        if records_count < page_size:
            return None
        key = config.get("param", "offset" if kind == "offset" else "page")
        # The request URL already includes the previous pagination parameter.
        # Rebuild from it, replacing rather than appending that value.
        parts = urlsplit(current_url)
        old_pairs = parse_qsl(parts.query, keep_blank_values=True)
        current = next((v for k, v in reversed(old_pairs) if k == key), None)
        previous = int(
            current
            if current is not None
            else config.get("start", 0 if kind == "offset" else 1)
        )
        next_value = previous + (page_size if kind == "offset" else 1)
        old_pairs = [(k, v) for k, v in old_pairs if k != key]
        next_url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(old_pairs),
                parts.fragment,
            )
        )
        new_parameters = {key: next_value}
        if kind not in {"offset", "page"}:
            raise ValueError("pagination.type must be next, offset or page")
        return next_url, new_parameters

    def _discover(self):
        url = self._expand(self.url)
        parameters = self._expand(self.req_parameters)
        if not isinstance(parameters, dict) and self.pagination.get("type") in {
            "page",
            "offset",
        }:
            raise ValueError("page/offset pagination requires dictionary parameters")
        body = self._expand(self.body)
        seen_pages, seen_assets = set(), set()
        max_pages = int(self.pagination.get("max_pages", 100))
        for page in range(max_pages):
            request_url = self._build_url(url, parameters)
            if request_url in seen_pages:
                raise ValueError("Pagination loop detected")
            seen_pages.add(request_url)
            content, final_url = self._request(url, parameters, body)
            response = json.loads(content)
            records = self._records(response)
            for record in records:
                if self.detail:
                    assets = self._fetch_detail(record, final_url)
                else:
                    asset = self._entry_from_record(record, final_url)
                    assets = [asset] if asset else []

                for asset in assets:
                    if not asset or asset[0] in seen_assets:
                        continue
                    href, filename, metadata = asset
                    seen_assets.add(href)
                    self.add_entry_to_results(
                        href, filename, self.data_type, metadata=metadata
                    )
                    if len(self.results) >= self.limit:
                        return
            upcoming = self._next(response, final_url, parameters, page, len(records))
            if upcoming is None:
                return
            url, parameters = upcoming
        raise ValueError(f"Pagination exceeded max_pages={max_pages}")

    def _response(self):
        url = self._expand(self.url)
        parameters = self._expand(self.req_parameters)
        body = self._expand(self.body)
        final_url = self._build_url(url, parameters)
        # Stable filenames across processes (unlike Python hash()).
        fingerprint = json.dumps(
            [final_url, self.method, body], sort_keys=True, default=str
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
        dst_fn = f"api_response_{digest}{self.out_ext}"
        if self.method == "GET":
            # Let Fetchez acquire the response in the normal fetch phase.
            # Headers may be needed again by the runtime fetcher.
            self.headers.update(self.req_headers)
            self.add_entry_to_results(
                final_url,
                dst_fn,
                "json" if self.out_ext in {".json", ".geojson"} else "file",
            )
        else:
            # POST bodies cannot be represented by Fetchez's normal GET entry;
            # materialize once and mark the local file as already downloaded.
            content, _ = self._request(url, parameters, body)
            path = Path(self._outdir) / dst_fn
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.add_entry_to_results(
                path.as_uri(),
                str(path),
                "json" if self.out_ext in {".json", ".geojson"} else "file",
                status=0,
            )

    def run(self):
        self.results = []
        self._discovery_failed = False
        try:
            if not self.url:
                raise ValueError("url is required")
            if self.mode == "discover":
                self._discover()
            else:
                self._response()
        except (
            ValueError,
            KeyError,
            TypeError,
            HTTPError,
            URLError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            self._discovery_failed = True
            self.status = -1
            logger.exception("REST API %s failed: %s", self.mode, exc)
        return self
