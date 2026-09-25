# test_spatial.py

import pytest
from fetchez.spatial import parse_region
from fetchez.spatial import Region


def test_parse_region_with_epsg():
    """Test parse_region with a region@epsg-code"""

    regions = parse_region("-R1/2/3/4@epsg:4326")
    assert len(regions) == 1
    assert regions[0].srs == "epsg:4326"


def test_region_warp_utm_to_wgs84():
    """Test that a projected region correctly transforms to WGS84 (EPSG:4326)."""

    # Approximate bounding box for Suva, Fiji in UTM Zone 60S (EPSG:32760)
    utm_region = Region(648000, 659000, 7987000, 7998000, srs="EPSG:32760")

    # Warp it in place
    utm_region.warp(dst_srs="EPSG:4326")

    assert utm_region.srs.upper() == "EPSG:4326"
    # Verify the coordinates shifted from meters to geographic degrees
    assert 177.0 < utm_region.xmin < 179.0
    assert -19.0 < utm_region.ymin < -17.0


def test_geo_transform_grid_node_handles_buffered_exact_cell_extent():
    region = Region(-117.25, -117.0, 28.0, 28.25).buffer(10)
    inc = 1.0 / 3600.0

    xcount, ycount, gt = region.geo_transform(
        x_inc=inc,
        y_inc=inc,
        node="grid",
    )

    assert region == Region(-117.275, -116.975, 27.975, 28.275)

    assert xcount == 1080
    assert ycount == 1080

    assert gt[0] == pytest.approx(-117.275)
    assert gt[1] == pytest.approx(inc)
    assert gt[3] == pytest.approx(28.275)
    assert gt[5] == pytest.approx(-inc)

    reconstructed = region.geo_transform_from_count(
        x_count=xcount,
        y_count=ycount,
    )

    assert reconstructed == pytest.approx(gt)
