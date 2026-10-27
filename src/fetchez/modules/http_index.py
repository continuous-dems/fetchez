#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.http_index
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generic HTTP link discovery with optional persistent FRED spatial indexing.

Configurable directory/project-page crawling; spatial footprints from filenames,
explicit bounds, or FGDC text metadata. No dataset downloads during discovery.
"""

import hashlib
import logging
import re
from collections import deque
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote

from fetchez import core, fred
from fetchez.cli import cli_opts
from fetchez.modules import FetchModule
from fetchez.spatial import Region

logger = logging.getLogger(__name__)
_BOUNDS = {
    key: re.compile(rf"{label}\s*:\s*([-+]?\d+(?:\.\d+)?)", re.I)
    for key, label in {
        "w": "West_Bounding_Coordinate",
        "e": "East_Bounding_Coordinate",
        "s": "South_Bounding_Coordinate",
        "n": "North_Bounding_Coordinate",
    }.items()
}


def _patterns(value):
    if not value:
        return []

    return [value] if isinstance(value, str) else list(value)


def _url_matches(url, patterns):
    name = unquote(Path(urlsplit(url).path).name)
    return any(
        fnmatch(name.lower(), pattern.lower()) or fnmatch(url.lower(), pattern.lower())
        for pattern in patterns
    )


def _safe_link(base, href, *, origin, prefix=None):
    url = urljoin(base, href).split("#", 1)[0]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None

    if _origin(url) != origin:
        return None

    if prefix and not parts.path.startswith(prefix):
        return None

    return url


def _origin(url):
    p = urlsplit(url)
    return (
        p.scheme.lower(),
        (p.hostname or "").lower(),
        p.port or (443 if p.scheme.lower() == "https" else 80),
    )


@cli_opts(
    help_text="Discover files from HTTP listings or project pages, optionally using a FRED index.",
    url="Starting HTTP(S) page or directory URL.",
    pattern="Glob filename patterns for downloadable assets (e.g. *.zip).",
    exclude="Optional glob patterns to skip.",
    follow_pattern="Glob patterns for catalog pages to follow.",
    recursive="Enable crawling linked pages.",
    max_depth="Maximum link-following depth.",
    index="Create/use a persistent spatial FRED GeoJSON.",
    index_name="Stable FRED GeoJSON basename, useful for YAML bundles.",
    update="Force rebuilding the index.",
    footprint="Optional mapping: method=filename|fgdc|static plus options.",
    filter_region="Filter by the requested region when footprints are available (default true).",
)
class HTTPIndex(FetchModule):
    name = "http_index"
    meta_category = "Generic"
    meta_desc = "Discover downloadable files from HTTP directories and HTML pages"
    meta_tags = ["http", "html", "index", "catalog", "scraper"]
    meta_provides = ["file", "raster", "vector", "archive"]
    meta_resolution = "varies"
    meta_license = "varies"

    def __init__(
        self,
        url=None,
        pattern=None,
        exclude=None,
        recursive=False,
        follow_pattern=None,
        max_depth=1,
        max_pages=200,
        max_assets=10000,
        index=False,
        index_name=None,
        index_path=None,
        update=False,
        footprint=None,
        data_type="file",
        metadata=None,
        filter_region=True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if not url or urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("url must be an HTTP(S) URL")

        self.url = url
        self.pattern = _patterns(pattern) or [
            "*.zip",
            "*.tar",
            "*.gz",
            "*.tif",
            "*.tiff",
            "*.nc",
            "*.laz",
            "*.las",
            "*.gpkg",
            "*.csv",
            "*.xyz",
            "*.txt",
        ]
        self.exclude = _patterns(exclude)
        self.recursive = bool(recursive)
        self.follow_pattern = _patterns(follow_pattern)
        self.max_depth = int(max_depth)
        self.max_pages = int(max_pages)
        self.max_assets = int(max_assets)
        self.use_index = bool(index)
        self.index_name = (
            index_name or "http_" + hashlib.sha256(url.encode()).hexdigest()[:12]
        )
        self.index_path = index_path
        self.update = bool(update)
        self.footprint = footprint or {}
        self.data_type = data_type
        self.entry_metadata = metadata or {}
        self.filter_region = bool(filter_region)
        if not isinstance(self.footprint, dict):
            raise ValueError("footprint must be a mapping")

        if self.max_depth < 0 or self.max_pages < 1 or self.max_assets < 1:
            raise ValueError(
                "max_depth must be >= 0; max_pages/max_assets must be positive"
            )

        if self.use_index and not self.footprint:
            raise ValueError("index=True requires a footprint configuration")

        if self.use_index and self.footprint.get("method") not in {
            "static",
            "filename",
            "fgdc",
        }:
            raise ValueError(
                "index=True requires footprint.method=static|filename|fgdc"
            )

    def _bbox(self, name, asset_url, page_url):
        cfg = self.footprint
        mode = cfg.get("method")
        if mode == "static":
            bounds = cfg["bounds"]  # Fetchez w/e/s/n order
            if len(bounds) != 4:
                raise ValueError("static footprint requires four bounds: w/e/s/n")

            region = Region(*map(float, bounds), srs="EPSG:4326")
            if not region.valid_p():
                raise ValueError("Invalid static footprint bounds")

            return region

        if mode == "filename":
            match = re.search(cfg["regex"], name)
            if match is None:
                return None

            parts = match.groupdict()
            if {"w", "e", "s", "n"} <= parts.keys():
                bounds = [float(parts[k]) for k in ("w", "e", "s", "n")]
            elif {"x", "y"} <= parts.keys():
                x, y = float(parts["x"]), float(parts["y"])
                dx, dy = float(cfg["width"]), float(cfg["height"])
                bounds = [x, x + dx, y, y + dy]
            else:
                raise ValueError("filename regex requires w/e/s/n or x/y named groups")

            region = Region(*bounds, srs="EPSG:4326")

            return region if region.valid_p() else None

        if mode == "fgdc":
            # Generic sibling metadata URL template; a provider can specify its path.
            template = cfg.get("url_template", "{stem}.txt")
            metadata_name = template.format(stem=Path(name).stem, filename=name)
            metadata_url = urljoin(page_url, metadata_name)
            if _origin(metadata_url) != _origin(self.url):
                return None

            try:
                page = core.Fetch(metadata_url).fetch_html()
                if page is None:
                    return None

                text = (
                    page.text_content() if hasattr(page, "text_content") else str(page)
                )
                coords = {k: pattern.search(text) for k, pattern in _BOUNDS.items()}
                if not all(coords.values()):
                    return None

                region = Region(
                    *(float(coords[k].group(1)) for k in ("w", "e", "s", "n")),
                    srs="EPSG:4326",
                )
                return region if region.valid_p() else None
            except Exception as exc:
                logger.debug("Could not parse FGDC metadata %s: %s", metadata_url, exc)
                return None

        if mode is None:
            return None

        raise ValueError(f"Unknown footprint method: {mode}")

    def _crawl(self):
        queue = deque([(self.url, 0)])
        seen_pages, seen_assets = set(), set()
        initial_origin = _origin(self.url)
        # Crawling stays on the initial origin. Restrict deeper paths in YAML
        # with follow_pattern; never automatically follow arbitrary site links.
        while queue:
            page_url, depth = queue.popleft()
            if page_url in seen_pages:
                continue

            if len(seen_pages) >= self.max_pages:
                raise RuntimeError("HTTP crawl exceeded max_pages")

            seen_pages.add(page_url)
            page = core.Fetch(page_url).fetch_html()
            if page is None:
                raise RuntimeError(f"Could not retrieve HTML listing {page_url}")

            for href in page.xpath("//a[@href]/@href"):
                asset_url = _safe_link(page_url, href, origin=initial_origin)
                if not asset_url:
                    continue

                if self.exclude and _url_matches(asset_url, self.exclude):
                    continue

                if _url_matches(asset_url, self.pattern):
                    if asset_url not in seen_assets:
                        seen_assets.add(asset_url)
                        yield asset_url, page_url

                    if len(seen_assets) >= self.max_assets:
                        return

                elif (
                    self.recursive
                    and depth < self.max_depth
                    and self.follow_pattern
                    and _url_matches(asset_url, self.follow_pattern)
                ):
                    queue.append((asset_url, depth + 1))

    def _query_region(self):
        """Return a region only when one was explicitly requested.

        FetchModule may provide a global WGS84 fallback for runs without -R.
        A directory crawl must not depend on that implicit fallback.
        """
        if not self.filter_region:
            return None

        init = getattr(self, "_init_kwargs", {})
        if init.get("region") is None:
            return None

        return self.wgs_region

    def _emit(self, url, name, metadata=None):
        self.add_entry_to_results(
            url=url,
            dst_fn=name,
            data_type=self.data_type,
            metadata={**self.entry_metadata, **(metadata or {})},
        )

    def run(self):
        self.results = []
        self._discovery_failed = False
        try:
            query_region = self._query_region()
            if self.use_index:
                index = fred.FRED(self.index_name, path=self.index_path)
                if index.features and not self.update:
                    for rec in index.search(region=query_region):
                        if rec.get("DataLink"):
                            self._emit(
                                rec["DataLink"],
                                rec.get("Name")
                                or Path(urlsplit(rec["DataLink"]).path).name,
                            )
                    return self

            discovered = []
            for url, page_url in self._crawl():
                name = unquote(Path(urlsplit(url).path).name)
                bounds = self._bbox(name, url, page_url) if self.footprint else None
                discovered.append((url, name, bounds))

            if self.use_index:
                index = fred.FRED(self.index_name, path=self.index_path)
                # Never overwrite a packaged or legacy shared index on refresh.
                if self.index_path is None:
                    index.path = Path.home() / ".fetchez" / "data" / index.filename

                features = []
                for url, name, bounds in discovered:
                    if bounds is None:
                        logger.debug("No footprint for %s; skipping FRED indexing", url)
                        continue

                    feature = {
                        "type": "Feature",
                        "geometry": bounds.to_geojson_geometry(),
                        "properties": {
                            "Name": name,
                            "ID": url,
                            "DataLink": url,
                            "DataSource": self.index_name,
                            "DataType": self.data_type,
                        },
                    }
                    features.append(feature)
                if not features:
                    raise RuntimeError(
                        "No usable spatial footprints; refusing empty FRED index"
                    )

                # Publish only after successful crawl/parse; preserve previous on errors.
                index.features = features
                index.save()
                for rec in index.search(region=query_region):
                    if rec.get("DataLink"):
                        self._emit(
                            rec["DataLink"],
                            rec.get("Name")
                            or Path(urlsplit(rec["DataLink"]).path).name,
                        )
            else:
                for url, name, bounds in discovered:
                    # Only filter where actual spatial coverage is known.
                    if bounds is not None and query_region is not None:
                        if not bounds.to_shapely().intersects(
                            query_region.to_shapely()
                        ):
                            continue

                    self._emit(url, name)
        except Exception as exc:
            self._discovery_failed = True
            self.status = -1
            logger.exception("HTTP discovery failed: %s", exc)

        return self
