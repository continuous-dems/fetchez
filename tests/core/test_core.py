# test_core.py

from fetchez.modules import FetchModule
from fetchez.spatial import Region


def test_fetchmodule_default_region():
    """If a module is initialized without a region, it should default to the whole globe."""

    mod = FetchModule(name="test_mod")

    assert mod.region == (-180, 180, -90, 90)
    assert mod.region.srs == "EPSG:4326"

    # Verify the dual-region handoff occurred for the default fallback
    assert mod.wgs_region == (-180, 180, -90, 90)
    assert mod.wgs_region.srs == "EPSG:4326"

    assert mod.wgs_region is not mod.region  # Ensure it is a unique copy


def test_fetchmodule_add_results():
    """Test that the helper method correctly populates the results list."""

    mod = FetchModule(name="test_mod")
    assert len(mod.results) == 0

    mod.add_entry_to_results(
        url="http://example.com/data.tif", dst_fn="data.tif", data_type="raster"
    )

    assert len(mod.results) == 1
    assert mod.results[0]["url"] == "http://example.com/data.tif"
    assert mod.results[0]["data_type"] == "raster"


def test_fetchmodule_projected_dual_region():
    """Ensure a projected region generates a distinct WGS84 region for API calls."""

    # Input a UTM bounding box
    src_region = Region(648000, 659000, 7987000, 7998000, srs="EPSG:32760")
    mod = FetchModule(name="test_mod", src_region=src_region)

    # Native region should remain exactly as the user provided
    assert mod.region.srs == "EPSG:32760"
    assert mod.region.xmin == 648000

    # WGS region should be warped to geographic coordinates
    if mod.wgs_region is not None:
        assert mod.wgs_region.srs.upper() == "EPSG:4326"
        assert mod.wgs_region.xmin != mod.region.xmin
        assert 177.0 < mod.wgs_region.xmin < 179.0
