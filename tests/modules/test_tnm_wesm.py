import os

import numpy as np
import pytest
import shapely
from pyproj import Transformer

from fetchez import spatial
from fetchez.modules import tnm_wesm


REGION = spatial.Region(0, 1, 0, 1, srs="EPSG:4326")


def _entry(project="Test_Project"):
    return {
        "url": f"https://example.test/Projects/{project}/tile.tif",
        "dst_fn": "tile.tif",
        "bounds": (0, 1, 0, 1),
        "tnm_project": project,
    }


def _index_row(project="Test_Project"):
    return {
        "fid": 1,
        "project": project,
        "project_id": "10",
        "workunit": project,
        "workunit_id": "20",
        "collect_start": "2020-01-01",
        "collect_end": "2020-12-31",
        "sourcedem_link": "",
        "_tnm_project": project,
    }


@pytest.fixture(autouse=True)
def reset_wesm():
    tnm_wesm.WESM.reset()


def test_legacy_one_ninth_filename_supplies_project_identity():
    entry = {"dst_fn": "ned19_n34x00_w118x00_CA_Orange_County_2016.zip"}

    assert tnm_wesm.project_name(entry) == "CA_Orange_County_2016"


def test_wesm_identity_accepts_omitted_cardinal_qualifier():
    aliases = {"CA_SanDiegoCo_2016": {"CA_SanDiegoCo_2016"}}
    row = {
        **_index_row("CA_Eastern_San_Diego_Co_Lidar_2016_B16"),
        "workunit": "CA_E_SanDiegoCo_2016",
        "sourcedem_link": (
            "https://prd-tnm.s3.amazonaws.com/index.html?prefix="
            "StagedProducts/Elevation/OPR/Projects/"
            "CA_Eastern_San_Diego_Co_Lidar_2016_B16/CA_E_SanDiegoCo_2016"
        ),
    }

    assert tnm_wesm._row_project(row, aliases) == "CA_SanDiegoCo_2016"


def test_directionless_wesm_identity_remains_fail_closed_when_ambiguous():
    aliases = {
        "CA_E_SanDiegoCo_2016": {"CA_E_SanDiegoCo_2016"},
        "CA_W_SanDiegoCo_2016": {"CA_W_SanDiegoCo_2016"},
    }
    row = {**_index_row("CA_SanDiegoCo_2016"), "workunit": "CA_SanDiegoCo_2016"}

    with pytest.raises(RuntimeError, match="matches multiple TNM projects"):
        tnm_wesm._row_project(row, aliases)


def test_wesm_index_snapshot_is_loaded_once(monkeypatch):
    row = _index_row()
    header = ",".join(tnm_wesm.WESM_FIELDS)
    values = ",".join(str(row[field]) for field in tnm_wesm.WESM_FIELDS)

    class Response:
        status_code = 200
        content = f"{header}\n{values}\n".encode()

    class Fetch:
        calls = 0

        def __init__(self, _url):
            pass

        def fetch_req(self, **kwargs):
            self.__class__.calls += 1
            return Response()

    monkeypatch.setattr(tnm_wesm.core, "Fetch", Fetch)

    first = tnm_wesm.WESM.index()
    second = tnm_wesm.WESM.index()

    assert first is second
    assert first[0]["fid"] == 1
    assert Fetch.calls == 1
    assert len(tnm_wesm.WESM.snapshot_sha256) == 64


def test_wesm_index_request_failure_raises(monkeypatch):
    class Response:
        status_code = 500
        content = b""

    class Fetch:
        def __init__(self, _url):
            pass

        def fetch_req(self, **kwargs):
            return Response()

    monkeypatch.setattr(tnm_wesm.core, "Fetch", Fetch)

    with pytest.raises(RuntimeError, match="WESM CSV request failed: 500"):
        tnm_wesm.WESM.index()


def test_missing_wesm_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "matching_rows",
        classmethod(lambda cls, aliases: []),
    )

    with pytest.raises(RuntimeError, match="no matching work-unit identity"):
        tnm_wesm.WESM.add_source_coverage([_entry()], REGION, require_year=True)


def test_matching_identity_outside_query_is_a_valid_nonintersection(monkeypatch):
    row = _index_row()
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "matching_rows",
        classmethod(lambda cls, aliases: [row]),
    )
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "features",
        classmethod(
            lambda cls, fids=None, bbox=None: [
                {**row, "geometry": shapely.box(2, 2, 3, 3)}
            ]
        ),
    )

    assert tnm_wesm.WESM.add_source_coverage([_entry()], REGION) == []


def test_matching_wesm_claim_is_attached_as_top_level_audit_data(monkeypatch):
    row = _index_row()
    tnm_wesm.WESM.snapshot_sha256 = "abc123"
    tnm_wesm.WESM.snapshot_retrieved_at = "2026-09-06T00:00:00+00:00"
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "matching_rows",
        classmethod(lambda cls, aliases: [row]),
    )
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "features",
        classmethod(
            lambda cls, fids=None, bbox=None: [
                {**row, "geometry": shapely.box(0.25, 0.25, 0.75, 0.75)}
            ]
        ),
    )

    selected = tnm_wesm.WESM.add_source_coverage([_entry()], REGION, require_year=True)

    assert len(selected) == 1
    assert selected[0]["tnm_source_coverage"][0]["year"] == 2020
    assert selected[0]["tnm_wesm_snapshot_sha256"] == "abc123"
    assert "tnm_source_coverage" not in selected[0].get("metadata", {})


def test_required_collection_year_fails_closed(monkeypatch):
    row = {**_index_row(), "collect_start": "", "collect_end": ""}
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "matching_rows",
        classmethod(lambda cls, aliases: [row]),
    )
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "features",
        classmethod(
            lambda cls, fids=None, bbox=None: [
                {**row, "geometry": shapely.box(0, 0, 1, 1)}
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="no collection year"):
        tnm_wesm.WESM.add_source_coverage([_entry()], REGION, require_year=True)


def test_feature_read_validates_csv_geopackage_identity(monkeypatch):
    row = _index_row()
    tnm_wesm.WESM._index = [row]
    meta = {"fields": list(tnm_wesm.WESM_FIELDS), "crs": "EPSG:4326"}
    fields = [
        np.array(["different" if field == "project" else row[field]])
        for field in tnm_wesm.WESM_FIELDS
    ]
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "_read",
        classmethod(
            lambda cls, **kwargs: (
                meta,
                np.array([1]),
                np.array([shapely.to_wkb(shapely.box(0, 0, 1, 1))]),
                fields,
            )
        ),
    )

    with pytest.raises(RuntimeError, match="changed between the CSV index"):
        tnm_wesm.WESM.features([1])


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3857"])
def test_feature_read_transforms_source_geometry_to_wgs84(monkeypatch, crs):
    row = _index_row()
    tnm_wesm.WESM._index = [row]
    expected = shapely.box(-67.0, 45.0, -66.9, 45.1)
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    geometry = shapely.Polygon(
        [transformer.transform(x, y) for x, y in expected.exterior.coords]
    )
    meta = {"fields": list(tnm_wesm.WESM_FIELDS), "crs": crs}
    fields = [np.array([row[field]]) for field in tnm_wesm.WESM_FIELDS]
    monkeypatch.setattr(
        tnm_wesm.WESM,
        "_read",
        classmethod(
            lambda cls, **kwargs: (
                meta,
                np.array([1]),
                np.array([shapely.to_wkb(geometry)]),
                fields,
            )
        ),
    )

    selected = tnm_wesm.WESM.features([1])

    assert len(selected) == 1
    assert selected[0]["fid"] == 1
    assert selected[0]["project"] == row["project"]
    assert selected[0]["geometry"].equals_exact(expected, tolerance=1e-9)


def test_wesm_gdal_environment_is_restored(monkeypatch):
    monkeypatch.setenv("AWS_NO_SIGN_REQUEST", "prior")
    monkeypatch.delenv("GDAL_DISABLE_READDIR_ON_OPEN", raising=False)

    with tnm_wesm.WESM._gdal_env():
        assert os.environ["AWS_NO_SIGN_REQUEST"] == "YES"
        assert os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"

    assert os.environ["AWS_NO_SIGN_REQUEST"] == "prior"
    assert "GDAL_DISABLE_READDIR_ON_OPEN" not in os.environ
