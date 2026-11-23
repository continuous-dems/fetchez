#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetchez.modules.sliderule
~~~~~~~~~~~~~~~~~~~~~~~~~

SlideRule server-side science processing as Fetchez acquisition entries.

The module's run() only builds a serializable request. The remote API is called
in fetch_entry(), allowing normal Fetchez acquisition and downstream hooks.

Optional dependencies: pip install sliderule geopandas pyarrow filelock

This is an initial integration, intentionally limited to GeoParquet outputs.
SlideRule's Python client maintains process-wide connection configuration; do
not concurrently use different service URLs/configurations in one process.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

import filelock

from fetchez import cli
from fetchez.core import FetchCancelled, FetchError
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

# Stable known API paths; 'run' is the newer generic dataframe-producing path.
_LEGACY = {
    "atl06p": ("icesat2", "atl06p"),
    "atl03sp": ("icesat2", "atl03sp"),
    "atl08p": ("icesat2", "atl08p"),
    "gedi01bp": ("gedi", "gedi01bp"),
    "gedi02ap": ("gedi", "gedi02ap"),
    "gedi04ap": ("gedi", "gedi04ap"),
}
_DATASETS = {"icesat2", "gedi"}
_CLIENT_LOCK = threading.RLock()


def _jsonable(obj):
    """Make a strict, cache-safe request without encoding opaque Python objects."""
    return json.loads(json.dumps(obj, sort_keys=True, allow_nan=False))


def _polygon(value):
    """Accept SlideRule lon/lat vertices, GeoJSON Polygon, or GeoJSON Feature."""
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get("type") == "Feature":
            return _polygon(value["geometry"])
        if value.get("type") != "Polygon":
            raise ValueError("polygon must be a GeoJSON Polygon/Feature or vertices")
        coords = value["coordinates"][0]
        value = coords
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError("polygon must contain at least three vertices")
    vertices = []
    for vertex in value:
        if isinstance(vertex, dict):
            lon, lat = vertex["lon"], vertex["lat"]
        else:
            lon, lat = vertex[:2]
        vertices.append({"lon": float(lon), "lat": float(lat)})
    if vertices[0] != vertices[-1]:
        vertices.append(dict(vertices[0]))
    return vertices


def _bbox_polygon(region):
    """Convert Fetchez's WGS84 bounds into SlideRule's poly format."""
    west, east, south, north = map(float, region)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("invalid WGS84 bounds (dateline-crossing bbox unsupported)")
    return _polygon([(west, south), (east, south), (east, north), (west, north)])


@cli.cli_opts(
    help_text="SlideRule remote ICESat-2/GEDI processing into local GeoParquet",
    dataset="SlideRule family: icesat2 or gedi",
    endpoint="SlideRule endpoint (atl06p, gedi04ap, atl06x, etc.)",
    parms="Native SlideRule processing parameters (YAML/JSON mapping)",
    polygon="Optional polygon in lon/lat vertices or GeoJSON Polygon",
    t0="Start time (passed to SlideRule processing parameters)",
    t1="End time (passed to SlideRule processing parameters)",
    resources="Optional explicit list of source granule filenames",
    url="SlideRule service hostname (default slideruleearth.io)",
    auth="none or auto (read SLIDERULE_GITHUB_TOKEN)",
)
class SlideRule(FetchModule):
    """Create remote-processing requests, materialized during acquisition."""

    name = "sliderule"
    meta_category = "Generic"
    meta_desc = "SlideRule server-side ICESat-2 and GEDI subset/processing"
    meta_agency = "SlideRuleEarth / NASA-funded science services"
    meta_region = "Global (subject to source coverage)"
    meta_resolution = "Varies"
    meta_license = "Source-product and service-specific"
    meta_tags = ["sliderule", "nasa", "icesat2", "gedi", "lidar", "remote-processing"]
    meta_urls = {
        "home": "https://slideruleearth.io/",
        "docs": "https://docs.slideruleearth.io/",
        "git": "https://github.com/SlideRuleEarth/sliderule",
    }
    # GeoParquet is intentionally classified as generic 'file' for now, in
    # agreement with earthaccess's existing .parquet mapping.
    meta_provides = ["file"]

    def __init__(
        self,
        dataset="icesat2",
        endpoint="atl06p",
        parms: dict | None = None,
        polygon=None,
        t0=None,
        t1=None,
        resources=None,
        url="slideruleearth.io",
        auth="none",
        output_format="parquet",
        output_name=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dataset = str(dataset).lower()
        self.endpoint = str(endpoint).lower()
        self.parms = dict(parms or {})
        self.polygon = polygon
        self.t0 = t0
        self.t1 = t1
        self.resources = resources
        self.url = str(url)
        self.auth = str(auth).lower()
        self.output_format = str(output_format).lower()
        self.output_name = output_name
        if self.dataset not in _DATASETS:
            raise ValueError(
                f"Unsupported dataset {self.dataset!r}; expected {_DATASETS}"
            )
        if self.auth not in {"none", "auto"}:
            raise ValueError("auth must be 'none' or 'auto'")
        if self.output_format != "parquet":
            raise ValueError(
                "Initial sliderule module supports output_format='parquet' only"
            )
        if self.endpoint in _LEGACY and _LEGACY[self.endpoint][0] != self.dataset:
            raise ValueError(
                f"Endpoint {self.endpoint!r} does not belong to {self.dataset!r}"
            )
        if not self.endpoint.replace("_", "").isalnum():
            raise ValueError("Invalid SlideRule endpoint name")
        if self.resources is not None and (
            not isinstance(self.resources, (list, tuple)) or not self.resources
        ):
            raise ValueError("resources must be a non-empty list of granule names")

    def _request(self):
        parms = _jsonable(self.parms)
        if "poly" in parms and self.polygon is not None:
            raise ValueError("Supply polygon either in parms.poly or polygon, not both")
        if self.polygon is not None:
            parms["poly"] = _polygon(self.polygon)
        elif "poly" not in parms and self.wgs_region is not None:
            parms["poly"] = _bbox_polygon(self.wgs_region)
        for key in ("t0", "t1"):
            value = getattr(self, key)
            if value is not None:
                if key in parms and parms[key] != value:
                    raise ValueError(f"Conflicting {key} in parms and module options")
                parms[key] = value
        if "poly" not in parms and not self.resources:
            raise ValueError(
                "SlideRule requires a Fetchez region, polygon, or resources"
            )
        # If the caller supplied a polygon directly through native parms,
        # preserve its semantics instead of unexpectedly rewriting it.
        spec = {
            "method": "sliderule",
            "dataset": self.dataset,
            "endpoint": self.endpoint,
            "url": self.url,
            "parms": parms,
            "resources": list(self.resources) if self.resources else None,
            "format": self.output_format,
        }
        return _jsonable(spec)

    def run(self):
        spec = self._request()
        canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
        request_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        filename = (
            self.output_name or f"sliderule_{self.endpoint}_{request_id[:16]}.parquet"
        )
        if Path(filename).name != filename or not filename.endswith(".parquet"):
            raise ValueError("output_name must be a basename ending in .parquet")
        self.add_entry_to_results(
            url=f"sliderule://{self.dataset}/{self.endpoint}/{request_id}",
            dst_fn=Path(self._outdir) / filename,
            data_type="file",
            acquisition=spec,
            metadata={"sliderule": {"request_id": request_id, "request": spec}},
        )
        return self

    def _check_cancelled(self):
        if self.context is not None and self.context.cancelled:
            raise FetchCancelled("SlideRule acquisition cancelled")

    def _execute(self, spec):
        try:
            import sliderule
        except ImportError as exc:
            raise ImportError(
                "SlideRule requires: pip install sliderule geopandas pyarrow"
            ) from exc
        # SlideRule init configuration can be global to the Python client.
        # This lock protects multiple Fetchez threads in this process.
        token = (
            os.environ.get("SLIDERULE_GITHUB_TOKEN") if self.auth == "auto" else None
        )
        init_options = {"url": spec["url"], "verbose": False}
        if token:
            init_options["github_token"] = token
        sliderule.init(**init_options)
        endpoint = spec["endpoint"]
        parms = dict(spec["parms"])
        resources = spec.get("resources")
        if endpoint in _LEGACY:
            family, method = _LEGACY[endpoint]
            api = __import__(f"sliderule.{family}", fromlist=[method])
            # Legacy parallel endpoints explicitly accept resources; the
            # generic run() path uses native parms and is used below.
            options = {"resources": resources} if resources is not None else {}
            result = getattr(api, method)(parms, **options)
        else:
            if resources is not None:
                raise ValueError(
                    "Explicit resources are currently supported only for known "
                    "legacy endpoints; place native selectors in parms for run()"
                )
            result = sliderule.run(endpoint, parms)
        if result is None or not hasattr(result, "to_parquet"):
            raise FetchError(f"SlideRule {endpoint} did not return a DataFrame")
        return result

    def fetch_entry(self, entry, check_size=True, retries=5, verbose=True):
        self._check_cancelled()
        spec = entry["acquisition"]
        if spec.get("method") != "sliderule":
            raise ValueError("Entry is not a SlideRule acquisition")
        output = Path(entry["dst_fn"])
        output.parent.mkdir(parents=True, exist_ok=True)
        with filelock.FileLock(f"{output}.lock", timeout=3600):
            self._check_cancelled()
            if output.is_file() and (not check_size or output.stat().st_size > 0):
                entry["status"] = 0
                return 0
            tmp_path = None
            try:
                with _CLIENT_LOCK:
                    self._check_cancelled()
                    result = self._execute(spec)
                    self._check_cancelled()
                    if len(result) == 0:
                        raise FetchError(
                            f"SlideRule {spec['endpoint']} returned no records for request"
                        )
                    with tempfile.NamedTemporaryFile(
                        dir=output.parent,
                        prefix=f".{output.name}.",
                        suffix=".parquet",
                        delete=False,
                    ) as tmp:
                        tmp_path = Path(tmp.name)
                    result.to_parquet(tmp_path, index=True)
                self._check_cancelled()
                if not tmp_path.is_file() or (
                    check_size and tmp_path.stat().st_size == 0
                ):
                    raise FetchError("SlideRule produced no valid output")
                tmp_path.replace(output)
                tmp_path = None
            except FetchCancelled:
                raise
            except Exception:
                logger.exception("SlideRule acquisition failed: %s", spec["endpoint"])
                raise
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)
        entry["status"] = 0
        return 0
