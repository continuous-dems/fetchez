import numpy as np
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin

from fetchez.modules import tnm_raster
from fetchez.spatial import Region


@pytest.fixture
def raster(monkeypatch, tmp_path):
    path = tmp_path / "s1m.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:6350",
        transform=from_origin(2240000, 2790000, 1000, 1000),
        nodata=-9999,
    ) as dst:
        # Interior NoData must not create fallback holes.
        dst.write(np.full((10, 10), -9999, dtype="float32"), 1)
    monkeypatch.setattr(tnm_raster.core, "HttpFile", lambda *a, **kw: open(path, "rb"))
    return {"url": "https://example.test/s1m.tif"}


def test_catalog_bbox_corner_is_not_raster_coverage(raster):
    assert (
        tnm_raster.add_source_coverage([raster], Region(-67, -66.99, 44.90, 44.93))
        == []
    )


def test_raster_extent_preserves_interior_nodata(raster):
    selected = tnm_raster.add_source_coverage(
        [raster], Region(-67.08, -67.07, 44.95, 44.96)
    )
    assert len(selected) == 1
    coverage = shapely.from_wkt(selected[0]["tnm_source_coverage"][0]["geometry"])
    assert coverage.equals(shapely.box(-67.08, 44.95, -67.07, 44.96))
