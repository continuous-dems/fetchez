#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Read authoritative USGS WESM source coverage for TNM products."""

import csv
import hashlib
import io
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import shapely
from pyogrio.raw import read
from pyproj import CRS, Transformer
from shapely.ops import transform as shapely_transform

from fetchez import core, spatial


WESM_CSV_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.csv"
)
WESM_GPKG_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.gpkg"
)
WESM_GPKG_PATH = "/vsis3/prd-tnm/StagedProducts/Elevation/metadata/WESM.gpkg"
WESM_LAYER = "WESM"
WESM_FIELDS = (
    "project",
    "project_id",
    "workunit",
    "workunit_id",
    "collect_start",
    "collect_end",
    "sourcedem_link",
)
WESM_IDENTITY_FIELDS = ("workunit", "workunit_id", "project", "project_id")
WESM_FEATURE_CHUNK_SIZE = 100
WESM_TIMEOUT = 60
WESM_RETRIES = 3

logger = logging.getLogger(__name__)


def _value(value):
    if value is None:
        return None
    value = str(value).strip()
    return None if not value or value.lower() == "nan" else value


def _path_names(value):
    if not isinstance(value, str):
        return []

    names = []
    for marker in ("/Projects/", "/metadata/"):
        if marker not in value:
            continue
        for part in value.split(marker, 1)[1].split("/"):
            part = part.split("?", 1)[0].strip()
            if part and part not in names:
                names.append(part)
    return names


def project_name(entry):
    """Return the TNM project identity exposed by the product itself."""

    project = _value(entry.get("tnm_project"))
    if project:
        return project

    for field in ("dst_fn", "url"):
        value = entry.get(field)
        if not isinstance(value, str):
            continue
        name = value.split("?", 1)[0].rsplit("/", 1)[-1]
        for suffix in (".zip", ".img", ".xml", ".txt", ".html"):
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
        match = re.match(r"^ned19_[^_]+_[^_]+_(.+)$", name, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def entry_names(entry):
    """Return provider-exposed names that may identify an entry in WESM."""

    names = []
    project = project_name(entry)
    if project:
        names.append(project)
    for field in ("tnm_vendor_meta_url", "tnm_meta_url", "url"):
        for name in _path_names(entry.get(field)):
            if name not in names:
                names.append(name)
    return names


def _row_names(row):
    names = []
    for field in ("workunit", "project"):
        value = _value(row.get(field))
        if value and value not in names:
            names.append(value)
    for name in _path_names(row.get("sourcedem_link")):
        if name not in names:
            names.append(name)
    return names


def _normalized_name(value, drop_compass=False):
    compass = {
        "eastern": "e",
        "northern": "n",
        "southern": "s",
        "western": "w",
    }
    tokens = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split()
    tokens = [compass.get(token, token) for token in tokens]
    if drop_compass:
        tokens = [token for token in tokens if token not in {"e", "n", "s", "w"}]
    return "".join(tokens) or None


def _row_project(row, aliases):
    row_names = set(_row_names(row))
    matches = [
        project for project, names in aliases.items() if row_names.intersection(names)
    ]
    if not matches:
        normalized = {_normalized_name(name) for name in row_names}
        normalized.discard(None)
        matches = [
            project
            for project, names in aliases.items()
            if normalized.intersection({_normalized_name(name) for name in names})
        ]
    if not matches:
        # TNM occasionally omits an otherwise authoritative cardinal qualifier
        # from its project directory (for example CA_SanDiegoCo_2016 versus the
        # WESM work unit CA_E_SanDiegoCo_2016).  Accept that provider naming
        # difference only when it identifies one TNM project unambiguously.
        directionless = {
            _normalized_name(name, drop_compass=True) for name in row_names
        }
        directionless.discard(None)
        matches = [
            project
            for project, names in aliases.items()
            if directionless.intersection(
                {_normalized_name(name, drop_compass=True) for name in names}
            )
        ]
    if len(matches) > 1:
        raise RuntimeError(
            "WESM work unit matches multiple TNM projects: "
            + ", ".join(sorted(matches))
        )
    return matches[0] if matches else None


def collection_year(row):
    for field in ("collect_end", "collect_start"):
        value = _value(row.get(field))
        if value is None:
            continue
        try:
            number = float(value)
        except ValueError:
            number = None
        if number is not None and number > 10_000_000_000:
            return datetime.fromtimestamp(number / 1000, timezone.utc).year
        match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", value)
        if match:
            return int(match.group(1))
    return None


def _same_identity(left, right):
    left = _value(left)
    right = _value(right)
    if left is None or right is None:
        return left is right
    try:
        return int(float(left)) == int(float(right))
    except ValueError:
        return left == right


class WESM:
    """One immutable WESM index snapshot shared by TNM modules in a process."""

    _index = None
    snapshot_sha256 = None
    snapshot_retrieved_at = None

    @classmethod
    def reset(cls):
        cls._index = None
        cls.snapshot_sha256 = None
        cls.snapshot_retrieved_at = None

    @staticmethod
    @contextmanager
    def _gdal_env():
        values = {
            "AWS_NO_SIGN_REQUEST": "YES",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".gpkg",
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        }
        previous = {name: os.environ.get(name) for name in values}
        os.environ.update(values)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    @classmethod
    def index(cls):
        if cls._index is not None:
            return cls._index

        try:
            response = core.Fetch(WESM_CSV_URL).fetch_req(
                tries=WESM_RETRIES,
                timeout=WESM_TIMEOUT,
                read_timeout=WESM_TIMEOUT,
            )
        except Exception as exc:
            raise RuntimeError("Unable to download the USGS WESM CSV index") from exc
        if response is None or response.status_code != 200 or not response.content:
            status = response.status_code if response is not None else "no response"
            raise RuntimeError(f"USGS WESM CSV request failed: {status}")

        payload = response.content
        try:
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
            missing = [field for field in WESM_FIELDS if field not in reader.fieldnames]
            if missing:
                raise RuntimeError(
                    "USGS WESM CSV index is missing required fields: "
                    + ", ".join(missing)
                )
            rows = []
            for fid, row in enumerate(reader, start=1):
                row["fid"] = fid
                rows.append(row)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Unable to read the USGS WESM CSV index") from exc
        if not rows:
            raise RuntimeError("USGS WESM CSV index contains no work units")

        cls._index = rows
        cls.snapshot_sha256 = hashlib.sha256(payload).hexdigest()
        cls.snapshot_retrieved_at = datetime.now(timezone.utc).isoformat()
        logger.debug(
            f"[tnm] Loaded WESM snapshot {cls.snapshot_sha256[:12]} ({len(rows)} rows)."
        )
        return rows

    @classmethod
    def matching_rows(cls, aliases):
        matches = []
        for row in cls.index():
            project = _row_project(row, aliases)
            if project is not None:
                values = dict(row)
                values["_tnm_project"] = project
                matches.append(values)
        return matches

    @classmethod
    def _read(cls, **kwargs):
        last_error = None
        for attempt in range(WESM_RETRIES):
            try:
                with cls._gdal_env():
                    return read(
                        WESM_GPKG_PATH,
                        layer=WESM_LAYER,
                        columns=list(WESM_FIELDS),
                        return_fids=True,
                        NOLOCK="YES",
                        IMMUTABLE="YES",
                        **kwargs,
                    )
            except Exception as exc:
                last_error = exc
                if attempt + 1 < WESM_RETRIES:
                    time.sleep(2**attempt)
        raise RuntimeError(
            "Unable to read USGS WESM GeoPackage geometry"
        ) from last_error

    @classmethod
    def features(cls, fids=None, bbox=None):
        index = {row["fid"]: row for row in cls.index()}
        options = {}
        if fids is not None:
            if not fids:
                return []
            values = ",".join(str(int(fid)) for fid in sorted(set(fids)))
            options["where"] = f"fid in ({values})"
        if bbox is not None:
            options["bbox"] = bbox

        meta, returned_fids, geometry_wkb, fields = cls._read(**options)
        names = list(meta.get("fields", []))
        if returned_fids is None or geometry_wkb is None:
            raise RuntimeError("USGS WESM GeoPackage returned no feature identities")
        returned = {int(fid) for fid in returned_fids}
        if fids is not None:
            missing = set(map(int, fids)).difference(returned)
            if missing:
                raise RuntimeError(
                    "USGS WESM GeoPackage is missing indexed FIDs: "
                    + ", ".join(map(str, sorted(missing)))
                )

        transformer = None
        crs = meta.get("crs")
        if crs and CRS.from_user_input(crs) != CRS.from_epsg(4326):
            transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        rows = []
        for offset, raw_fid in enumerate(returned_fids):
            fid = int(raw_fid)
            if fid not in index:
                raise RuntimeError(
                    f"WESM GeoPackage FID {fid} is absent from CSV index"
                )
            values = {name: fields[pos][offset] for pos, name in enumerate(names)}
            for field in WESM_IDENTITY_FIELDS:
                if not _same_identity(values.get(field), index[fid].get(field)):
                    raise RuntimeError(
                        "USGS WESM changed between the CSV index and GeoPackage "
                        f"geometry read for FID {fid} ({field})"
                    )
            geometry = shapely.from_wkb(geometry_wkb[offset])
            if geometry is None or geometry.is_empty:
                raise RuntimeError(
                    f"USGS WESM returned no usable polygon geometry for FID {fid}"
                )
            if transformer is not None:
                geometry = shapely_transform(transformer.transform, geometry)
            values["fid"] = fid
            values["geometry"] = geometry
            rows.append(values)
        return rows

    @classmethod
    def add_source_coverage(cls, entries, region, require_year=False):
        """Attach matching WESM claims and discard known non-intersections."""

        aliases = {}
        project_coverage = {}
        roi = spatial.region_to_shapely(region)
        for entry in entries:
            project = project_name(entry)
            bounds = entry.get("bounds")
            if not project:
                raise RuntimeError(
                    "TNM source coverage requires a provider project identity"
                )
            if not bounds or len(bounds) != 4 or any(value is None for value in bounds):
                raise RuntimeError("TNM source coverage requires product bounds")
            entry["tnm_project"] = project
            aliases.setdefault(project, set()).update(entry_names(entry))
            geometry = spatial.region_to_shapely(bounds).intersection(roi)
            if geometry.is_empty:
                continue
            current = project_coverage.get(project)
            project_coverage[project] = (
                geometry if current is None else shapely.union_all([current, geometry])
            )

        if not project_coverage:
            return []

        matches = cls.matching_rows(aliases)
        matched_projects = {row["_tnm_project"] for row in matches}
        missing = set(project_coverage).difference(matched_projects)
        if missing:
            raise RuntimeError(
                "USGS WESM has no matching work-unit identity for TNM project(s): "
                + ", ".join(sorted(missing))
            )

        by_fid = {row["fid"]: row for row in matches}
        features = []
        fids = sorted(by_fid)
        for offset in range(0, len(fids), WESM_FEATURE_CHUNK_SIZE):
            for row in cls.features(fids[offset : offset + WESM_FEATURE_CHUNK_SIZE]):
                row["_tnm_project"] = by_fid[row["fid"]]["_tnm_project"]
                features.append(row)

        query_coverage = shapely.union_all(list(project_coverage.values()))
        claims = []
        mismatches = []
        missing_year = []
        for row in features:
            project = row["_tnm_project"]
            coverage = project_coverage.get(project)
            if coverage is None:
                continue
            geometry = row["geometry"].intersection(query_coverage)
            if geometry.is_empty:
                continue
            geometry = geometry.intersection(coverage)
            if geometry.is_empty:
                mismatches.append(project)
                continue
            year = collection_year(row)
            if require_year and year is None:
                missing_year.append(project)
                continue
            claims.append((project, geometry, year, row))

        if mismatches:
            raise RuntimeError(
                "WESM source coverage matches TNM metadata but not its returned "
                "project tiles: " + ", ".join(sorted(set(mismatches)))
            )
        if missing_year:
            raise RuntimeError(
                "WESM has no collection year for TNM project(s): "
                + ", ".join(sorted(set(missing_year)))
            )

        selected = []
        for entry in entries:
            project = entry["tnm_project"]
            source = spatial.region_to_shapely(entry["bounds"]).intersection(roi)
            entry_claims = []
            for claim_project, geometry, year, row in claims:
                if claim_project != project:
                    continue
                coverage = geometry.intersection(source)
                if coverage.is_empty:
                    continue
                claim = {
                    "geometry": shapely.to_wkt(coverage, rounding_precision=-1),
                    "fid": int(row["fid"]),
                    "year": year,
                }
                for field in WESM_IDENTITY_FIELDS:
                    value = _value(row.get(field))
                    if value is not None:
                        claim[field] = value
                entry_claims.append(claim)
            if not entry_claims:
                continue
            entry["tnm_source_coverage"] = entry_claims
            entry["tnm_wesm_csv_url"] = WESM_CSV_URL
            entry["tnm_wesm_gpkg_url"] = WESM_GPKG_URL
            entry["tnm_wesm_snapshot_sha256"] = cls.snapshot_sha256
            entry["tnm_wesm_snapshot_retrieved_at"] = cls.snapshot_retrieved_at
            selected.append(entry)
        return selected
