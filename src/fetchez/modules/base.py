#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.base
~~~~~~~~~~~~~~~~~~~~~~

This holds the FetchModule super class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import time
import logging
import urllib.parse
import json
import hashlib
from pathlib import Path
from math import floor
from typing import List, Dict, Any

import pyproj

from fetchez import spatial
from fetchez import utils
from fetchez.core import Fetch

logger = logging.getLogger(__name__)


class FetchModule:
    """Base class for all Fetchez data modules."""

    # --- Registry Metadata (Override these in subclasses) ---
    name = "base_module"
    meta_category = "Generic"
    meta_desc = "Base module class."
    meta_agency = "Unknown"
    meta_tags: List[Any] = []
    meta_aliases: List[Any] = []
    meta_urls: Dict[Any, Any] = {}

    def __init__(
        self,
        src_region=None,
        hook=None,
        outdir=None,
        min_year=None,
        max_year=None,
        weight=1.0,
        uncertainty=0.0,
        params=None,
        use_cache=True,
        **kwargs,
    ):
        self.region = src_region.copy() if src_region else None
        self.wgs_region = None

        if self.region is not None and self.region.valid_p():
            # Generate the WGS region for fetching
            self.wgs_region = self.region.copy()

            if self.region.srs:
                is_geographic = False
                srs_str = str(self.region.srs).strip()

                try:
                    crs = pyproj.CRS.from_user_input(srs_str)
                    is_geographic = crs.is_geographic
                except Exception as e:
                    logger.debug(f"PyProj failed to parse CRS '{srs_str}': {e}")

                if not is_geographic:
                    srs_upper = srs_str.upper()
                    if any(
                        x in srs_upper
                        for x in ["4326", "4269", "+PROJ=LONGLAT", "GEOGCS"]
                    ):
                        is_geographic = True

                if not is_geographic:
                    logger.info(
                        f"Warping projected fetch region ({self.region.srs}) to EPSG:4326 for API queries..."
                    )
                    try:
                        self.wgs_region.warp(dst_srs="EPSG:4326")
                    except Exception as e:
                        logger.warning(
                            f"Failed to warp region to WGS84: {e}. APIs may fail."
                        )

        self.outdir = outdir
        self.params = params or {}
        self.status = 0
        self.results = []
        self.use_cache = use_cache

        # Store the parameters used to invoke this module for hashing
        self._init_kwargs = kwargs.copy()

        region_cache = None
        if src_region:
            if type(src_region).__name__ == "Region":
                region_cache = {
                    "__type__": "Region",
                    "w": src_region.w,
                    "e": src_region.e,
                    "s": src_region.s,
                    "n": src_region.n,
                    "srs": src_region.srs,
                }
            else:
                region_cache = list(src_region)

        self._init_kwargs.update(
            {
                "region": region_cache,
                "min_year": min_year,
                "max_year": max_year,
                "params": self.params,
            }
        )

        if self.outdir is None:
            self._outdir = str(Path.cwd().resolve() / self.name)
        else:
            self._outdir = str(Path(self.outdir).resolve() / self.name)

        self.stream_kwargs = {
            k: v for k, v in kwargs.items() if k not in ["datatype", "data_type"]
        }

        self.min_year = utils.int_or(min_year)
        self.max_year = utils.int_or(max_year)
        self.weight = utils.float_or(weight, 1.0)
        self.uncertainty = utils.float_or(uncertainty, 0.0)

        # Default Headers (Can be overridden in subclass)
        self.headers = {"User-Agent": "fetchez/0.5.0"}

        self.internal_hooks = []
        self.external_hooks = hook if hook else []

        # Default to the whole world if the region is invalid or missing.
        # Note: This will result in massive downloads for global datasets!
        if self.region is None or not spatial.region_valid_p(self.region):
            self.region = spatial.Region(-180, 180, -90, 90)
            self.region.srs = "EPSG:4326"
            self.wgs_region = self.region.copy()

        self.silent = logger.getEffectiveLevel() > logging.INFO

        self._original_run = self.run
        self.run = self._cached_run

    @property
    def hooks(self):
        """Combine internal and external hooks in the correct execution order."""

        return self.internal_hooks + self.external_hooks

    def add_hook(self, hook_obj):
        """Add a hook instance at runtime."""

        if hasattr(hook_obj, "run"):
            self.external_hooks.append(hook_obj)
        else:
            logger.warning(
                f"Hook {hook_obj} does not appear to be a valid FetchHook class."
            )

    def run(self):
        """Override this method in a subclass to populate `self.results`."""

        raise NotImplementedError("Subclasses must implement the `run` method.")

    def _generate_cache_key(self):
        """Generates a deterministic SHA-256 hash based on module properties."""

        # BLACKLIST
        ignored_keys = {
            "outdir",
            "hooks",
            "results",
            "status",
            "use_cache",
            "weight",
            "uncertainty",
            "name",
        }

        def _sanitize(val):
            """Recursively strip out un-hashable objects."""
            if isinstance(val, (str, int, float, bool, type(None))):
                return val
            if isinstance(val, Path):
                return str(val)
            if isinstance(val, (list, tuple)):
                cleaned = [_sanitize(v) for v in val]
                return [v for v in cleaned if v is not None]
            if isinstance(val, dict):
                cleaned = {str(k): _sanitize(v) for k, v in val.items()}
                return {k: v for k, v in cleaned.items() if v is not None}

            logger.debug(
                f"Cache warning: Cannot serialize object of type {type(val)}. Dropping from hash."
            )
            return None

        cache_dict = {}
        for key, val in self.__dict__.items():
            if key.startswith("_") or key in ignored_keys:
                continue

            # Handle the region tuple safely
            if key == "region" and val is not None:
                if type(val).__name__ == "Region":
                    cache_dict[key] = {
                        "__type__": "Region",
                        "w": val.w,
                        "e": val.e,
                        "s": val.s,
                        "n": val.n,
                        "srs": val.srs,
                    }

                continue

            clean_val = _sanitize(val)

            # Only add to the hash state if the value survived sanitization
            if clean_val is not None:
                # Exclude completely empty lists/dicts to keep the hash clean
                if isinstance(clean_val, (list, dict)) and not clean_val:
                    continue
                cache_dict[key] = clean_val

        logger.debug(f"\n--- {self.name} CACHE STATE ---")
        logger.debug(cache_dict)
        logger.debug(f"\n--- {self.name} CACHE STATE ---")

        state_str = json.dumps(cache_dict, sort_keys=True)
        return hashlib.sha256(state_str.encode("utf-8")).hexdigest()

    def _cached_run(self):
        """Intercepts run() to check the cache before querying remote APIs."""

        if not self.use_cache:
            return self._original_run()

        cache_dir = Path(self._outdir) / ".fetchez_cache"
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)

        cache_key = self._generate_cache_key()
        cache_file = Path(cache_dir) / f"{self.name}_{cache_key}.json"

        if cache_file.exists():
            try:
                file_age_days = floor(
                    (time.time() - cache_file.stat().st_mtime) / 86400
                )
                if file_age_days > 14:
                    logger.info(
                        f"[{self.name}] Using cached API response from {file_age_days} days ago."
                    )

                # Custom decoder to rebuild the Region object with its SRS
                def _json_object_hook(d):
                    if d.get("__type__") == "Region":
                        from fetchez.spatial import Region

                        return Region(d["w"], d["e"], d["s"], d["n"], srs=d.get("srs"))
                    return d

                cached_results = []
                with open(cache_file, "r") as f:
                    cached_results = json.load(f, object_hook=_json_object_hook)

                # Empty cache_results are useful, not sure if we should re-generate...
                # if cached_results:
                # Rehydrate relative paths to absolute paths for the current environment
                for entry in cached_results:
                    dst_fn = entry.get("dst_fn")
                    if dst_fn:
                        dst_fn = Path(dst_fn)
                        if not dst_fn.is_absolute():
                            dst_fn = Path(Path(self._outdir) / dst_fn)
                        entry["dst_fn"] = str(dst_fn.resolve())

                self.results = cached_results
                logger.debug(
                    f"[{self.name}] Loaded {len(self.results)} results from cache."
                )
                return self
            # logger.info(f"[{self.name}] Cached results are empty, creating a new one.")
            except Exception as e:
                logger.warning(f"[{self.name}] Cache corrupted, ignoring: {e}")

        # Cache file didn't exist, so we create a new one here.
        logger.debug(f"[{self.name}] Querying remote API...")
        self._original_run()

        def _json_fallback(obj):
            """Safely serialize custom objects like Region."""
            if type(obj).__name__ == "Region":
                return {
                    "__type__": "Region",
                    "w": obj.w,
                    "e": obj.e,
                    "s": obj.s,
                    "n": obj.n,
                    "srs": obj.srs,
                }
            if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
                return list(obj)
            return str(obj)

        try:
            # Create a localized copy of the results to safely store in the cache
            portable_results = []
            for entry in self.results:
                portable_entry = entry.copy()
                if "dst_fn" in portable_entry and portable_entry["dst_fn"]:
                    try:
                        # Strip the absolute prefix to make it portable relative to outdir
                        portable_entry["dst_fn"] = Path(
                            portable_entry["dst_fn"]
                        ).relative_to(Path(self._outdir))
                    except ValueError:
                        # Fallback for cross-drive path issues on Windows
                        pass
                portable_results.append(portable_entry)

            with open(cache_file, "w") as f:
                json.dump(portable_results, f, indent=2, default=_json_fallback)

            logger.debug(f"[{self.name}] Saved API results to cache.")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to save cache: {e}")
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.debug(f"Unable to remove cache_file: {cache_file}: {e}")
                    pass

        return self

    def fetch_entry(self, entry, check_size=True, retries=5, verbose=True):
        """Standardized method for fetching a single result entry."""

        try:
            parsed_url = urllib.parse.urlparse(entry["url"])
            module_auth = getattr(self, "auth", None)
            if parsed_url.scheme == "ftp":
                status = Fetch(
                    url=entry["url"],
                    headers=self.headers,
                    auth=module_auth,
                ).fetch_ftp_file(entry["dst_fn"])
            else:
                status = Fetch(
                    url=entry["url"],
                    headers=self.headers,
                    auth=module_auth,
                ).fetch_file(
                    entry["dst_fn"],
                    check_size=check_size,
                    tries=retries,
                    verbose=verbose,
                )
            entry["status"] = status

        except Exception as e:
            logger.error(f"Fetch failed for {entry['url']}: {e}")
            status = -1
            entry["status"] = status

        return status

    def add_entry_to_results(self, url: str, dst_fn: str, data_type: Any, **kwargs):
        """Add fetch entries to `results`.

        At minimum, `url`, `dst_fn` and `data_type` are required.
        Any additional keyword arguments will be added to the entry dictionary.
        """

        if utils.str_or(dst_fn):
            # Only join with outdir if dst_fn isn't already an absolute path
            if not Path(dst_fn).is_absolute():
                dst_fn = str(Path(self._outdir) / dst_fn)

        entry = {"url": str(url), "dst_fn": str(dst_fn), "data_type": data_type}

        if hasattr(self, "stream_kwargs"):
            entry.update(self.stream_kwargs)

        # Intercept standard spatial metadata fields
        standard_metadata = {
            "name": self.name,  # Module name (e.g., 'tnm', 'copernicus')
            "title": kwargs.pop("title", "Unknown"),
            "source": getattr(self, "meta_agency", "Unknown"),
            "date": kwargs.pop("date", "Unknown"),
            "data_type": data_type,
            "resolution": kwargs.pop(
                "resolution", getattr(self, "meta_resolution", "Unknown")
            ),
            "hdatum": kwargs.pop("hdatum", "Unknown"),
            "vdatum": kwargs.pop("vdatum", "Unknown"),
            "url": str(url),
        }
        entry_metadata = kwargs.pop("metadata", {})
        standard_metadata.update(entry_metadata)
        entry["metadata"] = standard_metadata

        entry.update(kwargs)
        self.results.append(entry)


# =============================================================================
# Core/Test Modules
# =============================================================================
class HttpDataset(FetchModule):
    """Fetch an HTTP/HTTPS file directly from a URL."""

    name = "url_fetcher"
    meta_category = "Generic"
    meta_desc = "Fetch a file directly from a URL."
    meta_resolution = "N/A"
    meta_license = "N/A"

    def __init__(self, url=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url

    def run(self):
        if self.url:
            self.add_entry_to_results(self.url, Path(self.url).name, "https")


class Scratch(FetchModule):
    """Scratch module that populates results directly from arguments."""

    name = "scratch"
    meta_category = "Reference"
    meta_desc = "Testing module that injects direct arguments into the pipeline."
    meta_resolution = "N/A"
    meta_license = "N/A"

    def __init__(self, url=None, path=None, datatype=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.path = path
        self.datatype = datatype

    def run(self):
        if self.url and self.path and self.datatype:
            self.add_entry_to_results(self.url, self.path, self.datatype)
