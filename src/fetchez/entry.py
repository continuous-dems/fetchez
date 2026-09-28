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
        "dst_fn",
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
