"""Regression and proposed-contract tests for fetchez.spatial.Region exports.

Run in the Fetchez checkout:
    pytest -q tests/spatial/test_region_formats.py

The tests prefixed ``test_proposed_`` describe enhancements discussed for Region:
``format('wkt')``, ``format('geojson')``, ``format('arcgis')``, and
``to_arcgis_envelope()``. They intentionally fail until implemented.
"""

import json

import pytest
from pyproj import CRS
from shapely.geometry import shape, box
from shapely import wkt

from fetchez.spatial import Region


@pytest.fixture
def region():
    return Region(-120.5, -117.0, 32.5, 34.5, srs="EPSG:4326")


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("gmt", "-R-120.5/-117.0/32.5/34.5"),
        ("bbox", "-120.5,32.5,-117.0,34.5"),
        ("region", "-120.5,-117.0,32.5,34.5"),
    ],
)
def test_format_bbox_styles(region, style, expected):
    # bbox_wesn is a proposed alias; existing 'region' must remain compatible.
    assert region.format(style) == expected


def test_format_bbox_wesn_alias(region):
    assert region.format("bbox_wesn") == region.format("region")


def test_format_default_remains_gmt(region):
    assert region.format() == region.format("gmt")


def test_to_bbox_order_and_type(region):
    result = region.to_bbox()
    assert isinstance(result, tuple)
    assert result == (-120.5, 32.5, -117.0, 34.5)


def test_to_list_order_and_type(region):
    result = region.to_list()
    assert isinstance(result, list)
    assert result == [-120.5, -117.0, 32.5, 34.5]


def test_to_shapely_is_rectangle(region):
    geometry = region.to_shapely()
    assert geometry.is_valid
    assert geometry.equals(box(-120.5, 32.5, -117.0, 34.5))


def test_to_wkt_is_valid_polygon(region):
    geometry = wkt.loads(region.to_wkt())
    assert geometry.equals(region.to_shapely())


def test_to_geojson_geometry_returns_native_dict(region):
    result = region.to_geojson_geometry()
    assert isinstance(result, dict)
    assert result["type"] == "Polygon"
    assert result["coordinates"][0][0] == result["coordinates"][0][-1]
    assert shape(result).equals(region.to_shapely())


def test_format_wkt_uses_existing_converter(region):
    assert wkt.loads(region.format("wkt")).equals(region.to_shapely())


def test_format_geojson_is_serialized_geometry(region):
    output = region.format("geojson")
    assert isinstance(output, str)
    assert shape(json.loads(output)).equals(region.to_shapely())


def test_to_arcgis_envelope_is_native_dict(region):
    envelope = region.to_arcgis_envelope()
    assert isinstance(envelope, dict)
    assert {k: envelope[k] for k in ("xmin", "ymin", "xmax", "ymax")} == {
        "xmin": -120.5,
        "ymin": 32.5,
        "xmax": -117.0,
        "ymax": 34.5,
    }
    assert envelope["spatialReference"]["wkid"] == 4326


def test_format_arcgis_serializes_structured_envelope(region):
    assert json.loads(region.format("arcgis")) == region.to_arcgis_envelope()


def test_arcgis_envelope_respects_projected_crs():
    region = Region(400000, 500000, 3600000, 3700000, srs="EPSG:32611")
    envelope = region.to_arcgis_envelope()
    assert envelope["spatialReference"]["wkid"] == 32611
    assert envelope["xmin"] == 400000
    assert envelope["ymax"] == 3700000


def test_arcgis_envelope_does_not_invent_crs():
    region = Region(-120, -119, 33, 34)
    envelope = region.to_arcgis_envelope()
    assert "spatialReference" not in envelope


def test_unresolvable_arcgis_crs_is_not_mislabeled():
    region = Region(0, 10, 0, 10, srs=CRS.from_epsg(4326).to_wkt())
    assert region.to_arcgis_envelope()["spatialReference"]["wkid"] == 4326


@pytest.mark.parametrize(
    "method", ["to_wkt", "to_geojson_geometry", "to_arcgis_envelope"]
)
def test_proposed_invalid_region_rejected_by_geometry_exports(method):
    invalid = Region(10, 0, 0, 10, srs="EPSG:4326")
    with pytest.raises(ValueError, match="(?i)invalid|bounds|region"):
        getattr(invalid, method)()


def test_partial_region_construction():
    region = Region()

    assert not region.valid_p()
    assert region.xmin is None


def test_export_methods_do_not_mutate_region(region):
    before = (tuple(region), region.srs)
    region.to_bbox()
    region.to_list()
    region.to_wkt()
    region.to_geojson_geometry()
    region.to_shapely()
    assert (tuple(region), region.srs) == before


def test_new_format_methods_do_not_mutate_region(region):
    before = (tuple(region), region.srs)
    region.to_arcgis_envelope()
    for style in ("wkt", "geojson", "arcgis"):
        region.format(style)
    assert (tuple(region), region.srs) == before
