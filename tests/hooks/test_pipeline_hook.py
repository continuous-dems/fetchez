"""Tests for the generic collection-stage child pipeline hook."""

from types import SimpleNamespace

import pytest

from fetchez.core import FetchContext
from fetchez.hooks.pipeline import Pipeline
from fetchez.recipe import Recipe, RecipeContext
from fetchez.spatial import Region


@pytest.fixture
def parent(tmp_path):
    region = Region(-120, -119, 33, 34)
    region.srs = "EPSG:4326"
    settings = RecipeContext(
        region=region,
        region_srs="EPSG:4326",
        name="parent",
        tile_dir=tmp_path / "tile",
        outdir=tmp_path / "output",
        shared_cache=tmp_path / "cache",
        refresh=True,
    )
    plan = SimpleNamespace(
        recipe_context=settings,
        region=region,
        config={"project": {"name": "parent"}, "region_srs": "EPSG:4326"},
        tile_dir=settings.tile_dir,
        shared_cache=settings.shared_cache,
        batch_name=None,
    )
    return FetchContext(plan=plan), settings


def install_fake_compiler(monkeypatch, *, artifact="dem", publish_path="dem.tif"):
    recorded = {}

    class ChildPlan:
        def execute(self, *, context, inputs=None):
            recorded["execution_context"] = context
            recorded["inputs"] = inputs
            if artifact is not None:
                context.artifacts.publish(
                    artifact, publish_path, metadata={"kind": "raster"}
                )
            return list(inputs or [])

    class FakeRecipe:
        def compile(self, recipe_context):
            recorded["recipe_context"] = recipe_context
            return ChildPlan()

    def fake_from_dict(cls, config):
        recorded["config"] = config
        return FakeRecipe()

    monkeypatch.setattr(Recipe, "from_dict", classmethod(fake_from_dict))
    return recorded


def test_pipeline_inherits_region_cache_and_isolates_directory(
    tmp_path, parent, monkeypatch
):
    parent_context, settings = parent
    recorded = install_fake_compiler(monkeypatch)
    hook = Pipeline(
        recipe={"project": {"name": "reference_dem"}}, publish={"ref": "dem"}
    )
    hook.context = parent_context
    source = [(object(), {"dst_fn": "original"})]
    assert hook.run(source) is source
    ctx = recorded["recipe_context"]
    assert ctx.region.to_list() == settings.region.to_list()
    assert ctx.region is not settings.region
    assert ctx.region_srs == settings.region_srs
    assert ctx.shared_cache == settings.shared_cache
    assert ctx.refresh is True
    assert ctx.tile_dir == (settings.tile_dir / "reference_dem").resolve()
    assert ctx.tile_dir.is_dir()
    assert recorded["inputs"] is None
    assert recorded["execution_context"].parent is parent_context
    assert parent_context.artifacts.get("ref").path == "dem.tif"
    assert parent_context.artifacts.get("ref").metadata == {"kind": "raster"}


def test_pipeline_forwards_entries_without_mutating_parent(parent, monkeypatch):
    parent_context, _ = parent
    recorded = install_fake_compiler(monkeypatch)
    hook = Pipeline(recipe={}, inputs=True)
    hook.context = parent_context
    entries = [(object(), {"metadata": {"weight": 1}})]
    assert hook.run(entries) is entries
    # The hook forwards current entries; FetchContext/run_fetchez owns the copy.
    assert recorded["inputs"] is entries
    assert parent_context.artifacts.names() == ()


def test_pipeline_explicit_region_overrides_inheritance(parent, monkeypatch):
    parent_context, _ = parent
    recorded = install_fake_compiler(monkeypatch)
    hook = Pipeline(
        recipe={"region": "-124/-123/40/41", "region_srs": "EPSG:4326"},
        context={"tile_dir": "refs"},
    )
    hook.context = parent_context
    hook.run([])
    ctx = recorded["recipe_context"]
    assert ctx.region.to_list() == [-124, -123, 40, 41]
    assert (
        ctx.tile_dir == (parent_context.plan.recipe_context.tile_dir / "refs").resolve()
    )


def test_missing_child_artifact_does_not_publish_partial_set(parent, monkeypatch):
    parent_context, _ = parent
    install_fake_compiler(monkeypatch)
    hook = Pipeline(recipe={}, publish={"valid": "dem", "missing": "other"})
    hook.context = parent_context
    with pytest.raises(KeyError, match="other"):
        hook.run([])
    assert parent_context.artifacts.names() == ()


def test_pipeline_rejects_invalid_context_and_options():
    with pytest.raises(TypeError, match="recipe"):
        Pipeline(recipe="reference.yaml")
    with pytest.raises(TypeError, match="inputs"):
        Pipeline(recipe={}, inputs="yes")
    with pytest.raises(ValueError, match="context"):
        Pipeline(recipe={}, context={"unknown": True})


def test_pipeline_rejects_runaway_nesting(parent, monkeypatch):
    root, _ = parent
    install_fake_compiler(monkeypatch)
    for _ in range(15):
        root = root.child(plan=object())
    hook = Pipeline(recipe={})
    hook.context = root
    with pytest.raises(Exception, match="Maximum nested pipeline depth"):
        hook.run([])
