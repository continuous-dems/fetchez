import pytest
from shapely.geometry import Polygon, MultiPolygon, Point, mapping


from fetchez.spatial import normalize_geometry, esri_geometry_to_shapely

esri = esri_geometry_to_shapely
normalize = normalize_geometry


def test_disjoint_shells_and_out_of_order_hole():
    shell_a = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
    shell_b = [(20, 0), (20, 10), (30, 10), (30, 0), (20, 0)]
    hole_b = [(22, 2), (28, 2), (28, 8), (22, 8), (22, 2)]
    geom = esri({"rings": [hole_b, shell_a, shell_b]})
    assert isinstance(geom, MultiPolygon)
    assert geom.area == pytest.approx(200 - 36)
    assert geom.is_valid


def test_geojson_and_point_and_esri_envelope():
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    assert normalize(mapping(poly)).equals(poly)
    assert normalize({"type": "Feature", "geometry": mapping(poly)}).equals(poly)
    assert normalize({"x": 5, "y": 6}).equals(Point(5, 6))
    assert normalize({"xmin": 0, "ymin": 0, "xmax": 2, "ymax": 2}).area == 4


def test_esri_projection():
    result = normalize(
        {"x": 0, "y": 0, "spatialReference": {"wkid": 3857}}, dst_crs="EPSG:4326"
    )
    assert result.equals(Point(0, 0))
    with pytest.raises(ValueError, match="Source CRS"):
        normalize({"x": 0, "y": 0}, dst_crs="EPSG:4326")


def test_reject_orphan_holes_and_ambiguous_bbox():
    hole = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    with pytest.raises(ValueError, match="no clockwise exterior"):
        esri({"rings": [hole]})
    with pytest.raises(TypeError, match="Unsupported"):
        normalize([0, 1, 0, 1])


def test_wkt_wkb_and_none():
    geom = Point(2, 3)
    assert normalize(geom.wkt).equals(geom)
    assert normalize(geom.wkb).equals(geom)
    assert normalize(None) is None
