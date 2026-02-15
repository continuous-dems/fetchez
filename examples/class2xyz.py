#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
class2xyz (fetchez hook) — LITE
-------------------------------

Extract LAS/LAZ points by classification and export to ASCII XYZ (X Y Z).

This hook is intentionally lightweight and does **not** perform CRS transforms.
For reprojection/gridding/stream chaining, use Globato hooks instead:

  stream_data → stream_reproject → save_xyz / simple_stack

Dependencies
------------
- Requires `laspy`
- For LAZ, also requires a LAZ backend such as `lazrs`

Install (recommended via conda-forge):
  mamba install -c conda-forge laspy lazrs
  # or: conda install -c conda-forge laspy lazrs

Output filename includes class code(s):
- classes=2            -> <tile>_c2.xyz
- classes=29           -> <tile>_c29.xyz
- classes=2|29|40      -> <tile>_c2-29-40.xyz
- classes not provided -> <tile>_call.xyz

Common examples:

  # 1) Topographic (ground) returns (class 2) -> XYZ (native CRS)
  fetchez <module> ... --hook class2xyz:classes=2,out_dir=./ground_xyz

  # 2) Bathymetric lidar (example: class 29) -> XYZ (native CRS)
  fetchez dav --survey_id 8688 ... --hook class2xyz:classes=29,out_dir=./bathy_xyz

Precision defaults (auto):
- If LAS/LAZ appears to be geographic (lon/lat) based on header bbox:
    XY precision -> 10 decimals
    Z precision  -> inferred from LAS header Z scale (e.g., 0.001 => 3 dp)
- Otherwise (projected meters):
    XY precision -> 3 decimals
    Z precision  -> inferred from LAS header Z scale

Overrides:
- precision=<int> sets BOTH xy_precision and z_precision
- xy_precision=<int> overrides X/Y only
- z_precision=<int> overrides Z only
- xy_geo_precision (default 10) / xy_proj_precision (default 3)

Notes:
- Output order is always X Y Z.
- If exporting in geographic CRS, X=lon and Y=lat.
- If outputs already exist, the hook will skip them unless overwrite=true.
"""

from __future__ import annotations

import hashlib
import re
import logging
import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from fetchez.hooks import FetchHook

# Log under fetchez.* so it shows up even when loaded from ~/.fetchez/hooks/
logger = logging.getLogger("fetchez.hooks.class2xyz")


def _as_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "yes", "y", "on"):
        return True
    if s in ("0", "false", "f", "no", "n", "off"):
        return False
    return default


def _as_int(v, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _parse_classes(v) -> Optional[List[int]]:
    """
    Parse a classification list.

    Note: fetchez hook arguments are comma-delimited (key=value,key=value,...),
    so **do not** use commas inside the `classes=` value. Prefer one of these:

      classes=2           (single class)
      classes=2|29|40     (multiple classes; recommended)
      classes=2+29+40     (multiple classes)
      classes=2;29;40     (multiple classes)

    This function accepts any of: comma, pipe, plus, semicolon, or whitespace as
    separators when the *entire* value arrives as a single string.
    """
    if v is None or v == "":
        return None
    if isinstance(v, (list, tuple)):
        out: List[int] = []
        for x in v:
            try:
                out.append(int(x))
            except Exception:
                pass
        return sorted(set(out)) if out else None
    if isinstance(v, int):
        return [v]

    s = str(v).strip()
    if not s:
        return None

    # Split on common separators. (Avoid commas in CLI values; use | or + instead.)
    toks = [t for t in re.split(r"[,\|\+;\s]+", s) if t]
    out: List[int] = []
    for tok in toks:
        out.append(int(tok))
    return sorted(set(out)) if out else None


def _is_las(fn: str) -> bool:
    ext = os.path.splitext(fn)[1].lower()
    return ext in (".las", ".laz")


def _safe_makedirs(d: str) -> None:
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _looks_geographic_bbox(xmin: float, xmax: float, ymin: float, ymax: float) -> bool:
    if any(map(lambda v: v is None or math.isnan(v), [xmin, xmax, ymin, ymax])):
        return False
    return (xmin >= -180.0 and xmax <= 180.0) and (ymin >= -90.0 and ymax <= 90.0)


def _dp_from_scale(scale: Optional[float], fallback: int = 3) -> int:
    """Infer decimal places from LAS header scale (e.g., 0.001 -> 3 dp)."""
    try:
        if scale is None or scale <= 0:
            return fallback
        p = -math.log10(scale)
        rp = round(p)
        if abs(p - rp) < 1e-9:
            return max(0, int(rp))
        return max(0, int(math.ceil(p)))
    except Exception:
        return fallback


def _class_tag(classes: Optional[List[int]]) -> str:
    if not classes:
        return "call"
    # already sorted/unique from _parse_classes
    return "c" + "-".join(str(c) for c in classes)


@dataclass
class _Counters:
    seen_las: int = 0
    produced_xyz: int = 0
    skipped_existing: int = 0
    empty_outputs: int = 0
    failed: int = 0


class Class2XYZ(FetchHook):
    name = "class2xyz"
    desc = "Extract LAS/LAZ points by classification and export to ASCII XYZ (X Y Z)."
    stage = "file"
    category = "lidar"

    def __init__(
        self,
        classes=None,
        out_dir=".",
        suffix="",  # optional extra suffix after class tag
        delimiter=" ",
        overwrite=False,
        unique=False,
        emit_entry=True,  # kept for backward-compat; currently unused
        skip_empty=True,
        chunk_size=2_000_000,
        # precision knobs
        precision=None,
        xy_precision=None,
        z_precision=None,
        xy_geo_precision=10,
        xy_proj_precision=3,
        **kwargs,
    ):
        # Explicitly reject CRS args if someone tries them anyway.
        if "in_srs" in kwargs or "out_srs" in kwargs:
            raise RuntimeError(
                "class2xyz (LITE) does not support CRS transforms (in_srs/out_srs).\n"
                "Use Globato instead, e.g.:\n"
                "  --hook stream_data:classes=<...> --hook stream_reproject:dst_srs=<...> --hook save_xyz\n"
            )

        super().__init__(**kwargs)

        self.classes = _parse_classes(classes)
        self.out_dir = str(out_dir) if out_dir is not None else "."
        self.suffix = str(suffix or "")
        self.delimiter = str(delimiter if delimiter is not None else " ")
        self.overwrite = _as_bool(overwrite, False)
        self.unique = _as_bool(unique, False)
        self.emit_entry = _as_bool(emit_entry, True)
        self.skip_empty = _as_bool(skip_empty, True)
        self.chunk_size = max(10_000, _as_int(chunk_size, 2_000_000))

        self._xy_geo_precision = _as_int(xy_geo_precision, 10)
        self._xy_proj_precision = _as_int(xy_proj_precision, 3)

        p_both = (
            None
            if precision is None or str(precision).strip() == ""
            else _as_int(precision, 3)
        )
        self._xy_precision_override = (
            None
            if xy_precision is None or str(xy_precision).strip() == ""
            else _as_int(xy_precision, 10)
        )
        self._z_precision_override = (
            None
            if z_precision is None or str(z_precision).strip() == ""
            else _as_int(z_precision, 3)
        )
        self._precision_both = p_both

        self._c = _Counters()
        self._warned_laspy = False
        self._warned_laz_backend = False
        self._logged_enabled = False

    def _mk_out_xyz(self, src_las: str) -> str:
        base = os.path.splitext(os.path.basename(src_las))[0]
        tag = _class_tag(self.classes)  # <-- class tag in filename
        if self.unique:
            base = f"{base}_{hashlib.sha1(src_las.encode('utf-8', 'ignore')).hexdigest()[:8]}"
        _safe_makedirs(self.out_dir)
        # filename: <base>_<tag><suffix>.xyz
        return os.path.join(self.out_dir, f"{base}_{tag}{self.suffix}.xyz")

    def _log_enabled_once(
        self, xy_dp: int, z_dp: int, geo: bool, z_scale: Optional[float]
    ):
        if self._logged_enabled:
            return
        cl = "ALL" if self.classes is None else ",".join(map(str, self.classes))
        logger.info(
            "class2xyz: enabled "
            f"(classes={cl}, out_dir={self.out_dir}, overwrite={self.overwrite}, "
            f"geo={geo}, xy_precision={xy_dp}, z_precision={z_dp}, z_scale={z_scale})"
        )
        self._logged_enabled = True

    def _infer_precisions_from_header(
        self, las_path: str
    ) -> Tuple[bool, int, int, Optional[float]]:
        try:
            import laspy  # type: ignore
        except Exception:
            geo = False
            xy_dp = self._xy_proj_precision
            z_dp = 3
            return geo, xy_dp, z_dp, None

        with laspy.open(las_path) as reader:
            hdr = reader.header
            try:
                xmin, ymin, _zmin = hdr.mins
                xmax, ymax, _zmax = hdr.maxs
            except Exception:
                xmin = ymin = xmax = ymax = float("nan")

            geo = _looks_geographic_bbox(
                float(xmin), float(xmax), float(ymin), float(ymax)
            )
            xy_default = self._xy_geo_precision if geo else self._xy_proj_precision

            z_scale_val: Optional[float] = None
            scales = getattr(hdr, "scales", None)
            if scales is not None and len(scales) >= 3:
                try:
                    z_scale_val = float(scales[2])
                except Exception:
                    z_scale_val = None
            z_default = _dp_from_scale(z_scale_val, fallback=3)

        if self._precision_both is not None:
            xy_default = self._precision_both
            z_default = self._precision_both
        if self._xy_precision_override is not None:
            xy_default = self._xy_precision_override
        if self._z_precision_override is not None:
            z_default = self._z_precision_override

        return geo, int(xy_default), int(z_default), z_scale_val

    def _run_laspy(
        self, las_path: str, out_xyz: str, xy_dp: int, z_dp: int
    ) -> Tuple[bool, int]:
        try:
            import laspy  # type: ignore
        except Exception:
            if not self._warned_laspy:
                logger.warning(
                    "class2xyz: laspy not installed. Install via conda-forge or pip:\n"
                    "  mamba install -c conda-forge laspy lazrs\n"
                    "  # or: pip install laspy lazrs\n"
                    "Skipping LAS/LAZ -> XYZ."
                )
                self._warned_laspy = True
            return False, 0

        try:
            las = laspy.open(las_path)
        except Exception as e:
            msg = str(e).strip()
            if las_path.lower().endswith(".laz") and not self._warned_laz_backend:
                msg += (
                    "\nclass2xyz hint: If this is a LAZ backend error, install lazrs:\n"
                    "  mamba install -c conda-forge lazrs\n"
                    "  # or: pip install lazrs"
                )
                self._warned_laz_backend = True
            logger.warning(
                f"class2xyz: failed to open {os.path.basename(las_path)} with laspy: {msg}"
            )
            return False, 0

        points_written = 0
        xfmt_pct = f"%.{xy_dp}f"
        yfmt_pct = f"%.{xy_dp}f"
        zfmt_pct = f"%.{z_dp}f"
        xfmt_py = f"{{:.{xy_dp}f}}"
        yfmt_py = f"{{:.{xy_dp}f}}"
        zfmt_py = f"{{:.{z_dp}f}}"

        if os.path.exists(out_xyz) and not self.overwrite:
            return True, 0

        try:
            with open(out_xyz, "w", encoding="utf-8") as f:
                for chunk in las.chunk_iterator(self.chunk_size):
                    if self.classes is not None:
                        try:
                            cls = chunk.classification
                        except Exception:
                            logger.warning(
                                f"class2xyz: no classification dimension in {las_path}"
                            )
                            return False, 0

                        try:
                            import numpy as np  # type: ignore

                            mask = np.isin(cls, self.classes)
                            if not mask.any():
                                continue
                            chunk = chunk[mask]
                        except Exception:
                            allowed = set(self.classes)
                            mask = [int(c) in allowed for c in cls]
                            if not any(mask):
                                continue
                            chunk = chunk[mask]

                    n = len(chunk)
                    if n == 0:
                        continue

                    x = chunk.x
                    y = chunk.y
                    z = chunk.z

                    # Fast path if numpy is available
                    try:
                        import numpy as np  # type: ignore

                        xs = np.char.mod(xfmt_pct, x)
                        ys = np.char.mod(yfmt_pct, y)
                        zs = np.char.mod(zfmt_pct, z)
                        lines = xs + self.delimiter + ys + self.delimiter + zs
                        f.write("\n".join(lines.tolist()))
                        f.write("\n")
                    except Exception:
                        for i in range(n):
                            f.write(
                                f"{xfmt_py.format(x[i])}{self.delimiter}"
                                f"{yfmt_py.format(y[i])}{self.delimiter}"
                                f"{zfmt_py.format(z[i])}\n"
                            )

                    points_written += n

        except Exception as e:
            logger.warning(f"class2xyz: failed writing {out_xyz}: {e}")
            return False, 0

        if self.skip_empty and points_written == 0:
            try:
                os.remove(out_xyz)
            except OSError:
                pass
            return True, 0

        return True, points_written

    def run(self, entries):
        out_entries: List[Tuple[object, dict]] = []

        for mod, entry in entries:
            out_entries.append((mod, entry))

            status = entry.get("status", 0)
            dst_fn = entry.get("dst_fn")

            if status != 0 or not dst_fn or not isinstance(dst_fn, str):
                continue
            if not _is_las(dst_fn):
                continue

            self._c.seen_las += 1

            geo, xy_dp, z_dp, z_scale = self._infer_precisions_from_header(dst_fn)
            self._log_enabled_once(xy_dp=xy_dp, z_dp=z_dp, geo=geo, z_scale=z_scale)

            out_xyz = self._mk_out_xyz(dst_fn)

            if os.path.exists(out_xyz) and not self.overwrite:
                self._c.skipped_existing += 1
                entry["class2xyz_out"] = out_xyz
                entry["class2xyz_classes"] = self.classes
                entry["class2xyz_backend"] = "existing"
                continue

            ok, _ = self._run_laspy(dst_fn, out_xyz, xy_dp=xy_dp, z_dp=z_dp)

            if not ok:
                self._c.failed += 1
                continue

            produced = os.path.exists(out_xyz) and (
                not self.skip_empty or os.path.getsize(out_xyz) > 0
            )
            if produced:
                self._c.produced_xyz += 1
                entry["class2xyz_out"] = out_xyz
                entry["class2xyz_classes"] = self.classes
                entry["class2xyz_backend"] = "laspy"
                entry["class2xyz_xy_precision"] = xy_dp
                entry["class2xyz_z_precision"] = z_dp
            else:
                self._c.empty_outputs += 1

        return out_entries

    def teardown(self):
        if self._c.seen_las == 0:
            logger.info("class2xyz: no LAS/LAZ files seen; nothing to do.")
            return

        if (
            self._c.produced_xyz == 0
            and self._c.skipped_existing > 0
            and self._c.failed == 0
        ):
            logger.info(
                f"class2xyz: reused existing XYZ outputs for {self._c.skipped_existing}/{self._c.seen_las} LAS/LAZ file(s) "
                f"(out_dir={self.out_dir})."
            )
            return

        if self._c.produced_xyz > 0:
            logger.info(
                f"class2xyz: wrote {self._c.produced_xyz} new XYZ file(s) "
                f"(reused={self._c.skipped_existing}, failed={self._c.failed}, empty_removed={self._c.empty_outputs}, "
                f"out_dir={self.out_dir})."
            )
            return

        logger.warning(
            "class2xyz: saw LAS/LAZ files but produced 0 XYZ outputs.\n"
            "Hints:\n"
            "  - Install laspy + lazrs:\n"
            "      mamba install -c conda-forge laspy lazrs\n"
            "  - If filtering by classes, verify the requested classes exist in the tiles.\n"
            f"Summary: seen_las={self._c.seen_las}, failed={self._c.failed}, empty_removed={self._c.empty_outputs}, out_dir={self.out_dir}."
        )
