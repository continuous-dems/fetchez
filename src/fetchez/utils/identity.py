"""Deterministic identity generation for Fetchez and its extensions."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonicalize(value: Any) -> Any:
    """Convert supported values into deterministic JSON-compatible data.

    Unsupported objects are rejected rather than reduced to repr() or
    their type names, which could produce unstable or colliding IDs.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Identity values must be finite.")
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("Identity mapping keys must be strings.")

        return {k: canonicalize(value[k]) for k in sorted(value)}

    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]

    if isinstance(value, (set, frozenset)):
        items = [canonicalize(item) for item in value]
        return sorted(items, key=canonical_json)

    raise TypeError(
        f"Unsupported identity value: {type(value).__name__}. "
        "Supply an explicit, deterministic representation."
    )


def canonical_json(value: Any) -> str:
    """Serialize identity data to a stable JSON representation."""
    return json.dumps(
        canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def make_id(
    namespace: str,
    *values: Any,
    length: int = 16,
    **fields: Any,
) -> str:
    """Generate a deterministic, namespaced identity.

    Parameters
    ----------
    namespace:
        Purpose of the identity, e.g. "globato:side_stack".
    *values:
        Optional ordered identity components.
    length:
        Number of hexadecimal SHA-256 characters to return.
    **fields:
        Explicit named identity components.

    Notes
    -----
    Does not read files, inspect runtime objects, or mutate entries.

    The namespace and canonicalization format are part of the
    identity contract. Changes may invalidate persisted identities.
    """
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("Identity namespace must be a non-empty string.")

    if namespace != namespace.strip():
        raise ValueError("Identity namespace cannot have surrounding whitespace.")

    if not isinstance(length, int) or isinstance(length, bool):
        raise TypeError("Identity length must be an integer.")

    if not 1 <= length <= 64:
        raise ValueError("Identity length must be between 1 and 64.")

    payload = {
        "namespace": namespace,
        "values": values,
        "fields": fields,
    }

    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    return f"{namespace}:{digest[:length]}"
