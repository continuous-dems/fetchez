"""Focused behavior tests for the set-srs hook's auto_utm option."""

from types import SimpleNamespace

from fetchez import utils
from fetchez.hooks.set_srs import SetSrs


def run_auto_utm(region, **kwargs):
    entry = {"dst_fn": "/data/survey.xyz"}
    SetSrs(horz_srs="auto_utm", **kwargs).run(
        [(SimpleNamespace(name="nos_hydro", region=region), entry)]
    )
    return entry["src_srs"]


def test_auto_utm_single_zone():
    assert run_auto_utm((-119.8, -119.2, 34.0, 34.5)) == "EPSG:32611"


def test_auto_utm_region_crossing_zones_uses_centre_zone():
    # Spans the zone 10 / zone 11 boundary at -120 degrees.
    assert run_auto_utm((-121.0, -119.6, 34.0, 35.0)) == "EPSG:32610"
    assert run_auto_utm((-120.4, -119.0, 34.0, 35.0), vert_srs="5703") == (
        "EPSG:32611+5703"
    )


def test_utm_zone_reports_primary_zone_when_crossing():
    info = utils.wgs84_to_utm_zone((-121.0, -119.6, -35.0, -34.0))

    assert info["crosses_zones"] is True
    assert info["primary_zone"] == 10
    assert info["primary_epsg"] == "EPSG:32710"
