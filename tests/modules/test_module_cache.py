# tests/modules/test_module_cache.py

from fetchez.modules.local_fs import LocalFS
from fetchez.spatial import Region


def test_module_id_changes_when_region_changes(tmp_path):
    region_a = Region(-120.4174, -120.3750, 32.4614, 32.5150)
    region_b = Region(-120.5, -120.25, 32.25, 32.5)

    module_a = LocalFS(outdir=tmp_path, src_region=region_a)
    module_b = LocalFS(outdir=tmp_path, src_region=region_b)

    first = module_a._generate_cache_key()
    second = module_b._generate_cache_key()

    assert first != second
