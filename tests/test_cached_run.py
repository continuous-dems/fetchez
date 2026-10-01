# tests/test_cached_run.py

from fetchez.modules.local_fs import LocalFS


def test_cached_run_returns_self_on_cache_miss(tmp_path):
    module = LocalFS(path=tmp_path, outdir="/tmp")

    result = module.run()

    assert result is module
    assert module.results


def test_cached_run_returns_self_on_cache_hit(tmp_path):
    first = LocalFS(outdir=tmp_path)
    first.run()

    second = LocalFS(outdir=tmp_path)
    result = second.run()

    assert result is second
    assert second.results == first.results


def test_run_return_contract_same_with_cache_disabled(tmp_path):
    module = LocalFS(outdir=tmp_path, use_cache=False)

    result = module.run()

    assert result is module
