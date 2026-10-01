from fetchez import spatial
from fetchez.modules import multibeam

REGION = spatial.Region(-121.30, -120.95, 35.45, 35.80, srs="EPSG:4326")


def _module(tmp_path, where="1=1"):
    return multibeam.MBDB(
        src_region=REGION, outdir=str(tmp_path), want_inf=False, where=where
    )


def test_mdbd_has_unique_identity_with_different_where(tmp_path):
    first = _module(tmp_path)
    second = _module(tmp_path, where="name=test")

    assert first._generate_cache_key() != second._generate_cache_key()


def test_mdbd_has_same_identity(tmp_path):
    first = _module(tmp_path)
    second = _module(tmp_path)

    assert first._generate_cache_key() == second._generate_cache_key()
