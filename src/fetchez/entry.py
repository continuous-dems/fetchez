#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.entry
~~~~~~~~~~~~~

Helpers and conventions for Fetchez pipeline entries.

A Fetchez entry is an extensible mapping representing a discovered dataset,
a fetched artifact, or a processing result. Fetchez reserves a defined set
of keys for core pipeline semantics, while extensions may add arbitrary
keys without interfering with the reserved vocabulary.

The entry remains a normal dictionary. This module provides the contract
around that dictionary rather than replacing it with a custom mapping type.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, date
from pathlib import Path
from typing import Any, Mapping


# =============================================================================
# Entry vocabulary
# =============================================================================

# Keys with framework-defined semantics.
#
# These are intentionally broader than the minimum required fields because
# they describe the evolving lifecycle of an entry.
ENTRY_KEYS = frozenset(
    {
        "url",
        "dst_fn",
        "data_type",
        "profile",
        "stream",
        "stream_type",
        "src_srs",
        "metadata",
        "artifacts",
        "status",
        "contribution_id",
        "geometry",
        "geometry_crs",
        "geometry_source",
        "geometry_kind",
        "geometry_type",
    }
)

# Keys expected on a normal module-produced entry.
REQUIRED_ENTRY_KEYS = frozenset(
    {
        "url",
        "dst_fn",
        "data_type",
    }
)

# Runtime/transient fields which should not participate in entry identity.
#
# `stream` may contain generators, readers, open datasets, etc.; `status`
# and `artifacts` are runtime products rather than intrinsic entry state.
ENTRY_RUNTIME_KEYS = frozenset(
    {
        "stream",
        "stream_type",
        "status",
        "artifacts",
    }
)

# Semantic fields used to construct an entry identity.
#
# This is intentionally explicit rather than hashing the entire dictionary.
# Extensions may attach arbitrary runtime or implementation-specific values
# without silently changing the identity semantics of core Fetchez.
ENTRY_IDENTITY_KEYS = frozenset(
    {
        "url",
        # "dst_fn",
        "data_type",
        "profile",
        "src_srs",
        "metadata",
    }
)


# =============================================================================
# Validation
# =============================================================================


def is_entry(value: Any) -> bool:
    """Return True when *value* is a mapping suitable for an entry.

    Entry objects remain ordinary mutable mappings. No subclass is required.
    """
    return isinstance(value, Mapping)


# Backwards-compatible short alias.
entry_p = is_entry


def validate_entry(
    entry: Mapping[str, Any],
    *,
    require: bool = True,
) -> None:
    """Validate the core Fetchez entry contract.

    Parameters
    ----------
    entry:
        Mapping representing a Fetchez entry.
    require:
        Require the minimum core fields when True.

    Raises
    ------
    TypeError
        If *entry* is not a mapping.
    ValueError
        If required fields are missing or have invalid values.
    """
    if not is_entry(entry):
        raise TypeError("Fetchez entry must be a mapping.")

    if not require:
        return

    missing = REQUIRED_ENTRY_KEYS - entry.keys()
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Fetchez entry is missing required keys: {missing_str}")

    if not entry.get("dst_fn"):
        raise ValueError("Fetchez entry requires a non-empty 'dst_fn'.")

    if not entry.get("data_type"):
        raise ValueError("Fetchez entry requires a non-empty 'data_type'.")


def _json_safe(value):
    """Convert common metadata types without mutating the source entry."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime, Path)):
        return str(value) if isinstance(value, Path) else value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__geo_interface__"):
        return _json_safe(value.__geo_interface__)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


# =============================================================================
# Identity
# =============================================================================


def _canonicalize(value: Any) -> Any:
    """Convert common Python values into deterministic JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]

    if isinstance(value, (set, frozenset)):
        return sorted(_canonicalize(item) for item in value)

    # Identity should never depend on repr() of arbitrary runtime objects.
    # Unsupported values are represented by their type rather than their
    # memory address or other process-specific state.
    return {
        "__type__": f"{type(value).__module__}.{type(value).__qualname__}",
    }


def canonical_entry_identity(entry: Mapping[str, Any]) -> str:
    """Return a deterministic representation of the semantic entry state.

    The result is suitable for hashing and is independent of dictionary
    insertion order.

    Only fields listed in ``ENTRY_IDENTITY_KEYS`` participate. Runtime fields
    such as streams, status, and artifacts are intentionally excluded.
    """
    validate_entry(entry, require=False)

    identity = {
        key: _canonicalize(entry[key])
        for key in sorted(ENTRY_IDENTITY_KEYS)
        if key in entry
    }

    return json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def entry_id(entry: Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 identity for the current entry state.

    This is a snapshot identity: because entries are intentionally mutable,
    calling ``entry_id()`` after a semantic change may produce a different ID.
    The ID is not stored on the entry itself.
    """
    identity = canonical_entry_identity(entry)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def source_id(entry: Mapping[str, Any]) -> str:
    """Return the canonical source identifier for an entry."""
    validate_entry(entry, require=False)

    url = entry.get("url")
    if not url:
        raise ValueError("Entry requires a non-empty 'url'.")

    return str(url)


def _get_all_keys(nested_dict):
    keys = []
    for key, value in nested_dict.items():
        keys.append(key)
        if isinstance(value, dict):
            keys.extend(_get_all_keys(value))
    return keys


def _base_dataset_id(entry: Mapping[str, Any]) -> str:
    """Return the best available stable identity for the underlying dataset."""
    validate_entry(entry, require=False)

    checksum = entry.get("checksum")
    if checksum:
        return str(checksum)

    url = entry.get("url")
    if url and not str(url).startswith("file://"):
        return str(url)

    dst_fn = entry.get("dst_fn")
    if dst_fn:
        path = Path(dst_fn)
        if path.exists() and path.is_file():
            return f"{path.name}|{path.stat().st_size}B"

    return source_id(entry)


def dataset_id(entry, **kwargs):
    base = _base_dataset_id(entry)

    contribution = entry.get("contribution_id") or {}

    if not contribution and not kwargs:
        return base

    modifiers = {
        "contribution": contribution,
        "kwargs": kwargs,
    }

    cannonical_modifiers = _canonicalize(modifiers)
    if "__type__" in _get_all_keys(cannonical_modifiers):
        raise TypeError(f"Cannot serialize {modifiers} in the dataset_id")

    payload = json.dumps(
        cannonical_modifiers,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    return f"{base}|{digest}"


# =============================================================================
# Reversible entry persistence (separate from identity canonicalization)
# =============================================================================

_ENTRY_TYPE_TAG = "__fetchez_type__"


def _serialize_value(value: Any) -> Any:
    """Convert supported entry values to JSON data without losing geometry."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        # Paths in cached entries have historically been stored as strings.
        return str(value)

    if type(value).__name__ == "Region":
        return {
            _ENTRY_TYPE_TAG: "Region",
            "w": value.w,
            "e": value.e,
            "s": value.s,
            "n": value.n,
            "srs": value.srs,
        }

    # Optional Shapely dependency: nonspatial entries do not import it.
    if hasattr(value, "__geo_interface__"):
        try:
            from shapely.geometry.base import BaseGeometry
        except ImportError:
            pass
        else:
            if isinstance(value, BaseGeometry):
                return {
                    _ENTRY_TYPE_TAG: "ShapelyGeometry",
                    "geometry": _serialize_value(value.__geo_interface__),
                }

    if isinstance(value, Mapping):
        return {str(k): _serialize_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]

    # NumPy scalar values are common in geospatial metadata.
    if hasattr(value, "item") and callable(value.item):
        converted = value.item()
        if converted is not value:
            return _serialize_value(converted)

    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()

    raise TypeError(f"Cannot serialize entry value of type {type(value).__name__}")


def _deserialize_value(value: Any) -> Any:
    """Reconstruct tagged values recursively, leaving ordinary JSON untouched."""
    if isinstance(value, list):
        return [_deserialize_value(item) for item in value]

    if not isinstance(value, dict):
        return value

    tag = value.get(_ENTRY_TYPE_TAG)
    if tag == "ShapelyGeometry" and set(value) == {_ENTRY_TYPE_TAG, "geometry"}:
        from shapely.geometry import shape

        return shape(value["geometry"])

    if tag == "Region" and set(value) == {_ENTRY_TYPE_TAG, "w", "e", "s", "n", "srs"}:
        from fetchez.spatial import Region

        return Region(value["w"], value["e"], value["s"], value["n"], srs=value["srs"])

    # Historical module caches used this Region marker.
    if value.get("__type__") == "Region" and {"w", "e", "s", "n"} <= value.keys():
        from fetchez.spatial import Region

        return Region(
            value["w"], value["e"], value["s"], value["n"], srs=value.get("srs")
        )

    return {key: _deserialize_value(item) for key, item in value.items()}


def serialize_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of an entry for caching or interchange.

    This is *not* identity canonicalization. Supported spatial objects retain
    explicit tags so they can be reconstructed by :func:`deserialize_entry`.
    Unsupported runtime objects raise TypeError rather than silently becoming
    misleading strings. The input is not mutated.
    """
    validate_entry(entry, require=False)
    return _serialize_value(entry)


def deserialize_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    """Rehydrate a serialized entry, including legacy cached WKT geometry."""
    if not isinstance(data, Mapping):
        raise TypeError("Serialized Fetchez entry must be a mapping")

    result = _deserialize_value(data)

    # Old _cached_run() stringified Shapely geometries. Restrict migration to
    # the canonical geometry field, never arbitrary metadata strings.
    geometry = result.get("geometry")
    if isinstance(geometry, str) and geometry.lstrip().upper().startswith(
        (
            "POLYGON ",
            "MULTIPOLYGON ",
            "POINT ",
            "MULTIPOINT ",
            "LINESTRING ",
            "MULTILINESTRING ",
            "GEOMETRYCOLLECTION ",
        )
    ):
        from shapely import wkt

        result["geometry"] = wkt.loads(geometry)

    return result


# =============================================================================
# Helpers
# =============================================================================


def set_contribution_id(entry, name, value):
    entry.setdefault("contribution_id", {})[name] = value
