# tests/test_gdal_vsi

from fetchez.core import gdal_vsi_path


def test_gdal_vsi_path_http():
    assert (
        gdal_vsi_path("https://example.com/data.tif")
        == "/vsicurl/https://example.com/data.tif"
    )


def test_gdal_vsi_path_ftp():
    assert (
        gdal_vsi_path("ftp://example.com/data.tif")
        == "/vsicurl/ftp://example.com/data.tif"
    )


def test_gdal_vsi_path_existing_vsi():
    path = "/vsicurl/https://example.com/data.tif"
    assert gdal_vsi_path(path) == path


def test_gdal_vsi_path_local():
    assert gdal_vsi_path("/tmp/data.tif") == "/tmp/data.tif"


def test_gdal_vsi_path_streaming():
    assert (
        gdal_vsi_path(
            "https://example.com/data.bin",
            streaming=True,
        )
        == "/vsicurl_streaming/https://example.com/data.bin"
    )
