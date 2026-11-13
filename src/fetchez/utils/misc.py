#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.misc
~~~~~~~~~~~~~~~~

Misc. utility functions for Fetchez.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import datetime
import getpass
import logging
from typing import Optional, Any, overload


logger = logging.getLogger(__name__)


# =============================================================================
# Data, Type and File Helpers
# =============================================================================
def this_date():
    """Get current date."""

    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def today_str() -> str:
    # "YYYY-MM-DD"
    return datetime.datetime.now().strftime("%Y-%m-%d")


def get_username() -> str:
    username = ""
    while not username:
        username = input("username: ")
    return username.strip()


def get_password() -> str:
    password = ""
    while not password:
        password = getpass.getpass("password: ")
    return password.strip()


def int_or(val: Any, or_val: Optional[int] = None) -> Optional[int]:
    """Return val if val is an integer, else return or_val"""

    try:
        int_val = float_or(val)
        if int_val is not None:
            return int(int_val)
        return or_val
    except Exception:
        return or_val


def float_or(val: Any, or_val: Optional[float] = None) -> Optional[float]:
    """Return val if val is a float, else return or_val"""

    try:
        return float(val)
    except Exception:
        return or_val


@overload
def str_or(instr: Any, or_val: str, replace_quote: bool = True) -> str: ...
@overload
def str_or(
    instr: Any, or_val: None = None, replace_quote: bool = True
) -> Optional[str]: ...
def str_or(
    instr: Any, or_val: Optional[str] = None, replace_quote: bool = True
) -> Optional[str]:
    """Return val if val is a string, else return or_val"""

    if instr is None:
        return or_val
    try:
        s = str(instr)
        return s.replace('"', "") if replace_quote else s
    except Exception:
        return or_val


def str2bool(v: Any) -> Optional[bool]:
    """Convert a string (or other type) to a boolean.

    Accepts:
      True:  'yes', 'true', 't', 'y', '1', 1, True
      False: 'no', 'false', 'f', 'n', '0', 0, False, None

    Args:
        v (str, int, bool): The value to convert.

    Returns:
        bool: The boolean representation of v.
    """

    if v is None:
        return None

    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        return bool(v)

    v_str = str(v).lower().strip()

    if v_str in ("yes", "true", "t", "y", "1"):
        return True
    elif v_str in ("no", "false", "f", "n", "0"):
        return False
    else:
        return None


def inc2str(inc: float) -> str:
    """Convert a WGS84 geographic increment to a string identifier."""

    import fractions

    return str(fractions.Fraction(str(inc * 3600)).limit_denominator(10)).replace(
        "/", ""
    )


def str2inc(value, crs="EPSG:4326", *, at=None, axis="x"):
    """Compatibility wrapper for `fetchez.spatial.parse_increment`."""
    from fetchez.spatial import parse_increment

    return parse_increment(value, crs=crs, at=at, axis=axis)


def x360(x: float) -> float:
    if x == 0:
        return -180
    elif x == 360:
        return 180
    else:
        return ((x + 180) % 360) - 180


# =============================================================================
# Hooks
# =============================================================================
def merge_hooks(global_hooks, local_hooks):
    """Merge global and local hooks.

    Order: Globals first, then Locals.

    Duplicate removal has been removed to allow nested sub-pipelines,
    but we log a debug warning if exact duplicates cross the global/local boundary.
    """

    import logging

    logger = logging.getLogger(__name__)

    merged = list(global_hooks)

    for h in local_hooks:
        if h in global_hooks:
            logger.debug(
                f"Duplicate hook '{h.name}' detected in both global and local scopes. "
                "Preserving both to support sequential sub-pipelines."
            )
        merged.append(h)

    return merged


# Depreciated due to removing duplicates!
def _merge_hooks(global_hooks, local_hooks):
    """Merge global and local hooks, removing exact duplicates.

    Order: Globals first, then Locals.
    """

    merged = []
    for h in global_hooks:
        if h not in merged:
            merged.append(h)

    for h in local_hooks:
        if h not in merged:
            merged.append(h)

    return merged


def _log_hook_history(entries, hook):
    """Append a history record to every entry in the list."""

    if not entries:
        return

    history_record = {
        "hook": hook.name,
        "stage": hook.stage,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    for _mod, entry in entries:
        if "history" not in entry:
            entry["history"] = []

        if entry["history"]:
            last = entry["history"][-1]
            if (
                last["hook"] == history_record["hook"]
                and last["stage"] == history_record["stage"]
            ):
                continue

        entry["history"].append(history_record.copy())


# =============================================================================
# Functions
# =============================================================================
def _linspace(start, stop, num=50):
    if num < 2:
        return [float(start)] if num == 1 else []

    # Calculate step size
    step = (stop - start) / (num - 1)

    # Generate the list
    return [start + i * step for i in range(num)]


def wgs84_to_utm_zone(region):
    """
    Determine UTM zone(s) for a WGS84 bounding box with EPSG codes.

    Args:
        region: region obj

    Returns:
        dict with zone info and EPSG codes
    """
    import math

    lon_min, lon_max, lat_min, lat_max = region

    # Calculate UTM zone numbers from longitude
    zone_min = int(math.floor((lon_min + 180) / 6)) + 1
    zone_max = int(math.floor((lon_max + 180) / 6)) + 1

    # Handle antimeridian crossing
    if zone_min > zone_max:
        zone_min, zone_max = 1, zone_max

    # Determine hemisphere
    is_north = lat_min >= 0
    hemisphere = "N" if is_north else "S"

    # Build EPSG codes
    def make_epsg_code(zone_num, is_north_hemisphere):
        prefix = 326 if is_north_hemisphere else 327
        return f"EPSG:{prefix}{zone_num:02d}"

    crosses_zones = zone_min != zone_max

    # The primary zone is the one holding the region's centre, so a region
    # that crosses a zone boundary still gets a usable EPSG code.
    if crosses_zones:
        east = lon_max + 360 if lon_max < lon_min else lon_max
        center_lon = ((lon_min + east) / 2 + 180) % 360 - 180
        primary_zone = min(int(math.floor((center_lon + 180) / 6)) + 1, 60)
    else:
        primary_zone = zone_min

    result = {
        "zone_min": zone_min,
        "zone_max": zone_max,
        "hemi": hemisphere,
        "crosses_zones": crosses_zones,
        "epsg_min": make_epsg_code(zone_min, is_north),
        "epsg_max": make_epsg_code(zone_max, is_north),
        "primary_zone": primary_zone,
        "primary_epsg": make_epsg_code(primary_zone, is_north),
    }

    return result
