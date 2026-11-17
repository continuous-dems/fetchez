"""Regression tests for catalog-aware Fetchez hooks."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fetchez.core import FetchContext
from fetchez.hooks.focus import FocusSink
from fetchez.hooks.exec import Exec
from fetchez.hooks.sidecar import Sidecar
from fetchez.hooks.copy_artifact import CopyArtifactHook
from fetchez.hooks.cloud_push import CloudPushHook


def module(name="source", instance_id="source-1"):
    return SimpleNamespace(name=name, instance_id=instance_id, tags=[])


def bind(hook, context):
    hook.context = context
    return hook


def test_exec_dual_publication_and_completed_output(tmp_path):
    ctx, mod = FetchContext(), module()
    src = tmp_path / "raw.txt"
    src.write_text("raw")
    entry = {"dst_fn": str(src), "status": 0}
    script = (
        "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('new')"
    )
    hook = bind(
        Exec(
            cmd=[sys.executable, "-c", script, "{output}"],
            output={"suffix": "_new", "extension": ".txt", "artifact_id": "processed"},
        ),
        ctx,
    )
    hook.run([(mod, entry)])
    record = ctx.artifacts.get("processed", owner=mod.instance_id)
    assert Path(record.path).read_text() == "new"
    assert str(entry["artifacts"]["processed"]) == record.path
    assert str(entry["dst_fn"]) == record.path


def test_exec_side_effect_does_not_publish(tmp_path):
    ctx, mod = FetchContext(), module()
    src = tmp_path / "raw.txt"
    src.write_text("raw")
    entry = {"dst_fn": str(src), "status": 0}
    hook = bind(Exec(cmd=[sys.executable, "-c", "pass"]), ctx)
    hook.run([(mod, entry)])
    assert not ctx.artifacts.find()
    assert "artifacts" not in entry


def test_sidecar_dual_publication(tmp_path):
    ctx, mod = FetchContext(), module()
    src = tmp_path / "tile.tif"
    src.write_bytes(b"test")
    entry = {"url": "file:///tile.tif", "dst_fn": str(src), "status": 0}
    bind(Sidecar(), ctx).run([(mod, entry)])
    record = ctx.artifacts.get("sidecar", owner=mod.instance_id)
    assert Path(record.path).exists()
    assert entry["artifacts"]["sidecar"] == record.path


def test_focus_merges_entry_and_catalog_artifacts_and_deduplicates(tmp_path):
    ctx, mod = FetchContext(), module()
    a, b = tmp_path / "a.tif", tmp_path / "b.tif"
    entries = [(mod, {"dst_fn": "input", "artifacts": {"dem": str(a)}})]
    ctx.artifacts.publish("dem", str(a), owner=mod.instance_id)
    ctx.artifacts.publish("dem", str(b), owner=mod.instance_id)
    result = bind(FocusSink(target="dem"), ctx).run(entries)
    assert [entry["dst_fn"] for _, entry in result] == [str(a), str(b)]
    assert all(owner is mod for owner, _ in result)


def test_focus_resolves_filtered_owner_through_recipe_plan(tmp_path):
    original, remaining = module("original", "a"), module("remaining", "b")
    ctx = FetchContext(
        plan=SimpleNamespace(modules_by_id={"a": original, "b": remaining})
    )
    path = tmp_path / "lost-but-registered.tif"
    ctx.artifacts.publish("dem", path, owner="a")
    result = bind(FocusSink(target="dem"), ctx).run([(remaining, {"dst_fn": "other"})])
    assert result[0][0] is original
    assert result[0][1]["dst_fn"] == str(path)


def test_focus_unresolved_owner_preserves_input(tmp_path, caplog):
    ctx, mod = FetchContext(), module()
    ctx.artifacts.publish("dem", tmp_path / "stray.tif", owner="unknown")
    original = [(mod, {"dst_fn": "input"})]
    assert bind(FocusSink(target="dem"), ctx).run(original) is original
    assert "unresolved module owner" in caplog.text


def test_copy_artifact_combines_catalog_and_legacy(tmp_path):
    ctx, mod = FetchContext(), module()
    a, b = tmp_path / "a_dem.tif", tmp_path / "b_dem.tif"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    entry = {"dst_fn": str(a), "artifacts": {"dem": str(a)}}
    ctx.artifacts.publish("dem", str(a), owner=mod.instance_id)
    ctx.artifacts.publish("dem", str(b), owner=mod.instance_id)
    dest = tmp_path / "collated"
    result = bind(CopyArtifactHook(target_dir=str(dest), match="dem.tif"), ctx).run(
        [(mod, entry)]
    )
    assert result == [(mod, entry)]
    assert sorted(p.name for p in dest.iterdir()) == ["a_dem.tif", "b_dem.tif"]


def test_copy_without_match_preserves_dst_fn_only_default(tmp_path):
    ctx, mod = FetchContext(), module()
    a, b = tmp_path / "input.tif", tmp_path / "other.tif"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    ctx.artifacts.publish("intermediate", str(b))
    dest = tmp_path / "collated"
    bind(CopyArtifactHook(target_dir=str(dest)), ctx).run([(mod, {"dst_fn": str(a)})])
    assert [p.name for p in dest.iterdir()] == ["input.tif"]


def test_cloud_push_uses_catalog_and_deduplicates(tmp_path, monkeypatch):
    ctx, mod = FetchContext(), module()
    a, b = tmp_path / "a_dem.tif", tmp_path / "b_dem.tif"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    ctx.artifacts.publish("dem", str(a))
    ctx.artifacts.publish("dem", str(b))
    calls = []
    monkeypatch.setattr(
        "fetchez.hooks.cloud_push.subprocess.run", lambda args, **kw: calls.append(args)
    )
    hook = bind(CloudPushHook(remote_dir="remote:archive", match="dem.tif"), ctx)
    hook.run([(mod, {"artifacts": {"dem": str(a)}})])
    assert {args[2] for args in calls} == {str(a), str(b)}
    assert len(calls) == 2


def test_raster_write_catalog_not_published_until_exhaustion(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    from rasterio.windows import Window
    from rasterio.transform import from_origin
    from fetchez.hooks.rasters.raster_writer import RasterWrite

    ctx, mod = FetchContext(), module()
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_origin(0, 2, 1, 1),
    }
    raster_context = SimpleNamespace(profile=profile, metadata={}, source=None)
    chunk = {
        "context": raster_context,
        "window": Window(0, 0, 2, 2),
        "data": np.ones((2, 2), dtype="uint8"),
        "band_index": 1,
    }
    entry = {
        "dst_fn": str(tmp_path / "original.tif"),
        "stream_type": "raster-stream",
        "stream": iter([chunk]),
    }
    hook = bind(
        RasterWrite(output_path=str(tmp_path / "final.tif"), artifact_id="dem"), ctx
    )
    hook.run([(mod, entry)])
    assert ctx.artifacts.find("dem") == []
    assert "artifacts" not in entry
    list(entry["stream"])
    assert ctx.artifacts.get("dem", owner=mod.instance_id).path == str(
        tmp_path / "final.tif"
    )
    assert entry["artifacts"]["dem"] == tmp_path / "final.tif"
