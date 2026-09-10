#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Read source footprints packaged with legacy USGS NED 1/9 arc-second DEMs."""

import hashlib
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import requests
import shapely
from pyogrio.raw import read
from pyproj import CRS, Transformer
from shapely.ops import transform as shapely_transform

from fetchez import core, spatial
from fetchez.modules.tnm_wesm import collection_year, project_name


def _read_footprint(url):
    for attempt in range(3):
        try:
            digest = hashlib.sha256(url.encode())
            with TemporaryDirectory(prefix="fetchez-ned-") as directory:
                with (
                    requests.Session() as session,
                    core.HttpFile(url, session=session) as remote,
                    zipfile.ZipFile(remote) as archive,
                ):
                    names = archive.namelist()
                    shapes = [name for name in names if name.lower().endswith(".shp")]
                    if len(shapes) != 1:
                        raise RuntimeError(
                            "NED archive must contain one source footprint"
                        )
                    source = shapes[0]
                    stem = str(PurePosixPath(source).with_suffix(""))
                    members = {name.lower(): name for name in names}
                    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                        member = members.get((stem + suffix).lower())
                        if member is None:
                            if suffix == ".cpg":
                                continue
                            raise RuntimeError(
                                f"NED source footprint is missing {suffix}"
                            )
                        payload = archive.read(member)
                        digest.update(member.encode())
                        digest.update(payload)
                        (Path(directory) / ("source" + suffix)).write_bytes(payload)
                return (
                    read(str(Path(directory) / "source.shp"), return_fids=True),
                    source,
                    digest.hexdigest(),
                )
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"Unable to read NED source footprint from {url}"
                ) from exc
            time.sleep(2**attempt)


def add_source_coverage(entries, region):
    """Attach packaged source polygons; omit only known non-intersections."""

    roi = spatial.region_to_shapely(region)
    selected = []
    digest = hashlib.sha256()
    for entry in entries:
        project = project_name(entry)
        if not project:
            raise RuntimeError(
                "TNM source coverage requires a provider project identity"
            )
        bounds = entry.get("bounds")
        if not bounds or len(bounds) != 4 or any(value is None for value in bounds):
            raise RuntimeError("TNM source coverage requires product bounds")
        url = entry["url"]
        (meta, fids, geometry_wkb, fields), member, checksum = _read_footprint(url)
        digest.update(checksum.encode())
        if not meta.get("crs"):
            raise RuntimeError("NED source footprint has no CRS")
        if fids is None or geometry_wkb is None or len(fids) == 0:
            raise RuntimeError("NED source footprint has no source features")
        names = [str(name).lower() for name in meta["fields"]]
        if len(geometry_wkb) != len(fids) or any(
            len(field) != len(fids) for field in fields
        ):
            raise RuntimeError("NED source footprint has incomplete source features")
        transformer = None
        if CRS.from_user_input(meta["crs"]) != CRS.from_epsg(4326):
            transformer = Transformer.from_crs(meta["crs"], "EPSG:4326", always_xy=True)
        source = spatial.region_to_shapely(bounds).intersection(roi)
        claims = []
        for offset, fid in enumerate(fids):
            row = {name: fields[pos][offset] for pos, name in enumerate(names)}
            identity = row.get("proj_name") or row.get("demname")
            if not isinstance(identity, str) or not identity.strip():
                raise RuntimeError("NED source footprint has no source identity")
            geometry = shapely.from_wkb(geometry_wkb[offset])
            if (
                geometry is None
                or geometry.geom_type not in ("Polygon", "MultiPolygon")
                or geometry.is_empty
                or not geometry.is_valid
            ):
                raise RuntimeError("NED source footprint has invalid polygon geometry")
            if transformer is not None:
                geometry = shapely_transform(transformer.transform, geometry)
            coverage = geometry.intersection(source)
            if coverage.is_empty or coverage.area == 0:
                continue
            claims.append(
                {
                    "geometry": shapely.to_wkt(coverage, rounding_precision=-1),
                    "fid": int(fid),
                    "project": str(row.get("proj_name") or project),
                    "source_dem": str(row["demname"]) if row.get("demname") else None,
                    "year": collection_year({"collect_start": row.get("s_date")}),
                }
            )
        if not claims:
            continue
        entry["tnm_project"] = project
        entry["tnm_source_coverage"] = claims
        entry["tnm_ned_source_url"] = f"{url}#{member}"
        selected.append(entry)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    for entry in selected:
        entry["tnm_ned_snapshot_sha256"] = digest.hexdigest()
        entry["tnm_ned_snapshot_retrieved_at"] = retrieved_at
    return selected
