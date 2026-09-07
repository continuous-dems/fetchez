import io
import zipfile

import numpy as np
import pytest
import shapely
from pyogrio.raw import write
from pyproj import Transformer
from shapely.ops import transform

from fetchez import spatial
from fetchez.modules import tnm_ned


REGION = spatial.Region(0, 1, 0, 1, srs="EPSG:4326")


def _entry():
    return {
        "url": (
            "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/19/IMG/"
            "ned19_n45x00_w067x00_me_northcoast_2010.zip"
        ),
        "bounds": (0, 1, 0, 1),
    }


def _archive(tmp_path, nested=False, omit=None):
    path = tmp_path / "footprint.shp"
    fields = (
        {
            "proj_name": "AK_Juneau_2013",
            "demname": None,
            "s_date": 2013,
            "resolution": 100,
        }
        if nested
        else {"DEMNAME": "me_nelot1_dem", "S_DATE": 2010, "RESOLUTION": 19}
    )
    write(
        path,
        np.array([shapely.to_wkb(shapely.box(0.25, 0.25, 0.75, 0.75))]),
        [np.array([value]) for value in fields.values()],
        list(fields),
        driver="ESRI Shapefile",
        geometry_type="Polygon",
        crs="EPSG:4269",
    )
    buffer = io.BytesIO()
    prefix = "ned19_n58x25_w134x00/" if nested else ""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in sorted(tmp_path.glob("footprint.*")):
            if member.suffix != omit:
                archive.write(member, prefix + member.name)
        archive.writestr(prefix + "raster.img", b"raster must not be read")
    return buffer.getvalue(), prefix + path.name


@pytest.mark.parametrize("nested", [False, True])
def test_reads_actual_flat_and_nested_footprints_without_raster(
    monkeypatch, tmp_path, nested
):
    payload, source = _archive(tmp_path, nested)
    monkeypatch.setattr(tnm_ned.core, "HttpFile", lambda *a, **k: io.BytesIO(payload))
    original = zipfile.ZipFile.read
    members = []

    def read_member(archive, name, *args, **kwargs):
        members.append(name)
        return original(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", read_member)
    selected = tnm_ned.add_source_coverage([_entry()], REGION)
    claim = selected[0]["tnm_source_coverage"][0]
    assert claim["year"] == (2013 if nested else 2010)
    assert claim["source_dem"] == (None if nested else "me_nelot1_dem")
    if nested:
        assert claim["project"] == "AK_Juneau_2013"
    assert shapely.from_wkt(claim["geometry"]).equals(
        shapely.box(0.25, 0.25, 0.75, 0.75)
    )
    assert selected[0]["tnm_ned_source_url"] == _entry()["url"] + "#" + source
    assert len(selected[0]["tnm_ned_snapshot_sha256"]) == 64
    assert "tnm_wesm_snapshot_sha256" not in selected[0]
    assert all(not member.endswith(".img") for member in members)


@pytest.mark.parametrize("omit", [".shp", ".shx", ".dbf", ".prj"])
def test_missing_archive_metadata_fails_after_bounded_retries(
    monkeypatch, tmp_path, omit
):
    payload, _ = _archive(tmp_path, omit=omit)
    calls = []

    def remote(*args, **kwargs):
        calls.append(1)
        return io.BytesIO(payload)

    monkeypatch.setattr(tnm_ned.core, "HttpFile", remote)
    monkeypatch.setattr(tnm_ned.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="Unable to read NED source footprint"):
        tnm_ned.add_source_coverage([_entry()], REGION)
    assert len(calls) == 3


def _raw(monkeypatch, geometry=None, crs="EPSG:4326", identity="me_nelot1_dem"):
    if geometry is None:
        geometry = shapely.box(0.25, 0.25, 0.75, 0.75)
    result = (
        {"crs": crs, "fields": ["DEMNAME", "S_DATE"]},
        [0],
        [shapely.to_wkb(geometry)],
        [[identity], [2010]],
    )
    monkeypatch.setattr(
        tnm_ned, "_read_footprint", lambda _: (result, "source.shp", "abc")
    )


def test_known_source_outside_roi_is_omitted(monkeypatch):
    _raw(monkeypatch, shapely.box(2, 2, 3, 3))
    assert tnm_ned.add_source_coverage([_entry()], REGION) == []


def test_missing_source_identity_fails_closed(monkeypatch):
    _raw(monkeypatch, identity=None)
    with pytest.raises(RuntimeError, match="no source identity"):
        tnm_ned.add_source_coverage([_entry()], REGION)


def test_missing_crs_fails_closed(monkeypatch):
    _raw(monkeypatch, crs=None)
    with pytest.raises(RuntimeError, match="no CRS"):
        tnm_ned.add_source_coverage([_entry()], REGION)


@pytest.mark.parametrize(
    "geometry",
    [
        shapely.Point(0.5, 0.5),
        shapely.Polygon(),
        shapely.Polygon([(0, 0), (1, 1), (1, 0), (0, 1)]),
    ],
)
def test_invalid_polygon_raises(monkeypatch, geometry):
    _raw(monkeypatch, geometry)
    with pytest.raises(RuntimeError, match="invalid polygon geometry"):
        tnm_ned.add_source_coverage([_entry()], REGION)


def test_projected_footprint_is_clipped_to_tile_and_roi(monkeypatch):
    geometry = transform(
        Transformer.from_crs(4326, 3857, always_xy=True).transform,
        shapely.box(-1, -1, 2, 2),
    )
    _raw(monkeypatch, geometry, crs="EPSG:3857")
    region = spatial.Region(0.5, 1.5, 0.5, 1.5, srs="EPSG:4326")
    selected = tnm_ned.add_source_coverage([_entry()], region)
    geometry = shapely.from_wkt(selected[0]["tnm_source_coverage"][0]["geometry"])
    assert geometry.equals(shapely.box(0.5, 0.5, 1, 1))
