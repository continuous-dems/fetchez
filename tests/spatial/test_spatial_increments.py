"""Tests for CRS-aware GMT-style increments (fetchez.spatial)."""

import pytest
from fetchez.spatial import parse_increments
from fetchez.utils import str2inc


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10", 10),
        ("100", 100),
        ("0.0010", 0.001),
        ("1e-3", 0.001),
        ("1.0e-3", 0.001),
        ("1E+3", 1000),
        (0.5, 0.5),
        ("1d", 1),
        ("30m", 0.5),
        ("15s", 15 / 3600),
        ("15c", 15 / 3600),
    ],
)
def test_geographic_and_numeric(value, expected):
    assert parse_increments(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "none",
        "0",
        0,
        "0s",
        "-1",
        "-1s",
        "10S",
        "10x",
        "nan",
        "inf",
        "10mm",
        "1/2",
    ],
)
def test_invalid(value):
    assert parse_increments(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10e", 10),
        ("100f", 30.48),
        ("1k", 1000),
        ("1M", 1609.344),
        ("1n", 1852),
        ("1u", 1200 / 3937),
        ("10t", 10),
    ],
)
def test_linear_to_utm(value, expected):
    assert parse_increments(value, crs="EPSG:32611") == pytest.approx(expected)


def test_geographic_linear_default_at_equator():
    assert parse_increments("10e") == pytest.approx(parse_increments("10e", at=(0, 0)))
    assert 0.00008 < parse_increments("10e") < 0.0001


def test_geographic_linear_latitude_and_axis():
    x_equator = parse_increments("100e", at=(0, 0), axis="x")
    x_midlat = parse_increments("100e", at=(-117, 45), axis="x")
    y_midlat = parse_increments("100e", at=(-117, 45), axis="y")
    assert x_midlat > x_equator
    assert y_midlat > 0


def test_projected_angular_requires_reference():
    with pytest.raises(ValueError, match="at="):
        parse_increments("1s", crs="EPSG:32611")


def test_projected_angular_with_reference():
    x = parse_increments("1s", crs="EPSG:32611", at=(-117, 33), axis="x")
    y = parse_increments("1s", crs="EPSG:32611", at=(-117, 33), axis="y")
    assert 20 < x < 30
    assert 28 < y < 33


def test_projected_feet_crs():
    # NAD83 / California zone 6 (ftUS)
    assert parse_increments("100e", crs="EPSG:2230") == pytest.approx(100 * 3937 / 1200)


def test_compatibility_wrapper():
    assert str2inc("15s") == pytest.approx(parse_increments("15s"))
    assert str2inc("10e", crs="EPSG:32611") == pytest.approx(10)


def test_unsupported_crs_and_axis():
    with pytest.raises(ValueError):
        parse_increments("1s", crs="not-a-crs")
    with pytest.raises(ValueError):
        parse_increments("1s", axis="z")
