#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.base
~~~~~~~~~~~~~~~~~~~~~~

This holds the FetchModule super class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import time
import logging
import urllib.parse
import json
import hashlib
import tempfile
from pathlib import Path
from math import floor
from typing import List, Dict, Any, Mapping

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

    # The kinds of data entries this module can provide.
    meta_provides: List[Any] = []

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
        # A module sets this when discovery failed without raising (for
        # example an API outage). The results are then not an answer and
        # `_cached_run` will not cache them.
        self._discovery_failed = False

        # Store the normalized invocation configuration used for module identity.
        region_config = None
        if src_region:
            if type(src_region).__name__ == "Region":
                region_config = {
                    "__type__": "Region",
                    "w": src_region.w,
                    "e": src_region.e,
                    "s": src_region.s,
                    "n": src_region.n,
                    "srs": src_region.srs,
                }
            else:
                region_config = list(src_region)

        # Store the parameters used to invoke this module for hashing
        self._init_kwargs = {
            **kwargs,
            "region": region_config,
            "min_year": min_year,
            "max_year": max_year,
            "weight": weight,
            "uncertainty": uncertainty,
            "params": self.params,
        }

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

    def clear_hooks(self):
        self.internal_hooks = []
        self.external_hooks = []

    def run(self):
        """Override this method in a subclass to populate `self.results`."""

        raise NotImplementedError("Subclasses must implement the `run` method.")

    # =============================================================================
    # MODULE IDENTITY / CACHE
    # =============================================================================

    # Runtime/configuration fields which should not participate in module identity.
    #
    # These describe execution state or the execution environment rather than
    # the requested module operation.
    _MODULE_ID_IGNORED = frozenset(
        {
            "outdir",
            "hooks",
            "results",
            "status",
            "use_cache",
        }
    )

    _MODULE_ID_DEFAULTS = {
        "region": None,
        "min_year": None,
        "max_year": None,
        "weight": 1.0,
        "uncertainty": 0.0,
        "params": {},
    }

    @classmethod
    def _canonicalize_module_value(cls, value: Any) -> Any:
        """Convert a value into a deterministic JSON-safe representation."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Path):
            return str(value)

        if type(value).__name__ == "Region":
            return {
                "__type__": "Region",
                "w": value.w,
                "e": value.e,
                "s": value.s,
                "n": value.n,
                "srs": value.srs,
            }

        if isinstance(value, Mapping):
            return {
                str(key): cls._canonicalize_module_value(val)
                for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            }

        if isinstance(value, (list, tuple)):
            return [cls._canonicalize_module_value(item) for item in value]

        if isinstance(value, (set, frozenset)):
            values = [cls._canonicalize_module_value(item) for item in value]
            return sorted(
                values,
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":")
                ),
            )

        # Never allow repr() of arbitrary objects to introduce process-specific
        # memory addresses into identity.
        return {"__type__": (f"{type(value).__module__}.{type(value).__qualname__}")}

    @classmethod
    def canonical_module_config_from_kwargs(
        cls,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Return canonical module configuration from constructor arguments."""
        config = dict(kwargs)

        # Historical alias normalization.
        if "data_type" in config and "datatype" in config:
            config.pop("datatype", None)
        elif "datatype" in config:
            config["data_type"] = config.pop("datatype")

        # Execution-only settings.
        for key in cls._MODULE_ID_IGNORED:
            config.pop(key, None)

        # Normalize region alias.

        region = config.pop("src_region", config.pop("region", None))

        if region is not None:
            if type(region).__name__ == "Region":
                config["region"] = {
                    "__type__": "Region",
                    "w": region.w,
                    "e": region.e,
                    "s": region.s,
                    "n": region.n,
                    "srs": region.srs,
                }
            else:
                config["region"] = list(region)

        # Remove values equivalent to canonical defaults.
        for key, default in cls._MODULE_ID_DEFAULTS.items():
            if key in config and config[key] == default:
                config.pop(key)

        config["name"] = cls.name

        return cls._canonicalize_module_value(config)

    def canonical_module_config(self) -> Dict[str, Any]:
        """Return canonical configuration for this module invocation."""
        return self.canonical_module_config_from_kwargs(**self._init_kwargs)

    @classmethod
    def _module_id_from_config(cls, config: Mapping[str, Any]) -> str:
        payload = {
            "module": f"{cls.__module__}.{cls.__qualname__}",
            "config": config,
        }

        state = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def _update_module_config(self, **kwargs):
        self._init_kwargs.update(kwargs)

    def module_id(self) -> str:
        """Return a deterministic ID for this module invocation."""
        return self._module_id_from_config(self.canonical_module_config())

    @classmethod
    def module_id_from_kwargs(cls, **kwargs):
        return cls._module_id_from_config(
            cls.canonical_module_config_from_kwargs(**kwargs)
        )

    def _generate_cache_key(self) -> str:
        """Return the module identity used by the persistent API cache."""
        return self.module_id()

    def _cached_run(self):
        """Intercepts run() to check the cache before querying remote APIs."""

        self._discovery_failed = False
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

        if getattr(self, "_discovery_failed", False):
            logger.debug(f"[{self.name}] Discovery failed; results not cached.")
            return self

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

        tmp_path = None

        try:
            portable_results = []

            for entry in self.results:
                portable_entry = entry.copy()

                if portable_entry.get("dst_fn"):
                    try:
                        portable_entry["dst_fn"] = Path(
                            portable_entry["dst_fn"]
                        ).relative_to(Path(self._outdir))
                    except ValueError:
                        pass

                portable_results.append(portable_entry)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cache_dir,
                prefix=f".{cache_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

                json.dump(
                    portable_results,
                    tmp_file,
                    indent=2,
                    default=_json_fallback,
                )
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_path, cache_file)
            tmp_path = None

            logger.debug(f"[{self.name}] Saved API results to cache.")

        except Exception as e:
            logger.warning(f"[{self.name}] Failed to save cache: {e}")

            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as cleanup_error:
                    logger.debug(
                        f"Unable to remove temporary cache file "
                        f"{tmp_path}: {cleanup_error}"
                    )

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
