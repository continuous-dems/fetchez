"""Regression tests for implicit local_fs sources in Recipe compilation.

These tests describe the intended shorthand contract; they will fail until
local-source normalization is implemented in Recipe.
"""

from pathlib import Path

import pytest

from fetchez.hooks import FetchHook
from fetchez.modules import FetchModule
from fetchez.recipe import Recipe
from fetchez.registry import (
    BundleRegistry,
    HookRegistry,
    ModifierRegistry,
    ModuleRegistry,
    PresetRegistry,
    SchemaRegistry,
)


class LocalSource(FetchModule):
    name = "local_fs"

    def __init__(self, src_region=None, hook=None, path=None, ext=None):
        self.src_region = src_region
        self.hook = hook if hook is not None else []
        self.path = path
        self.ext = ext


class NamedSource(FetchModule):
    name = "named-source"

    def __init__(self, src_region=None, hook=None):
        self.src_region = src_region
        self.hook = hook if hook is not None else []


class LocalHook(FetchHook):
    name = "local-hook"

    def __init__(self, marker=None):
        self.marker = marker


@pytest.fixture
def local_registry(monkeypatch):
    """Exercise Recipe compilation without loading plugins or fetching data."""
    for registry in (
        BundleRegistry,
        HookRegistry,
        ModifierRegistry,
        ModuleRegistry,
        PresetRegistry,
        SchemaRegistry,
    ):
        monkeypatch.setattr(registry, "load_all", lambda: None)

    monkeypatch.setattr(
        ModuleRegistry,
        "get_class",
        lambda name: {"local_fs": LocalSource, "named-source": NamedSource}.get(name),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        lambda name: {"local-hook": LocalHook}.get(name),
    )
    monkeypatch.setattr(PresetRegistry, "expand_hooks", lambda defs, **kw: defs)

    # Model the expansion interface: it turns shorthand strings into module
    # dictionaries but otherwise preserves entries and their arguments.
    monkeypatch.setattr(
        BundleRegistry,
        "expand_modules",
        lambda defs, **kw: [
            {"module": item} if isinstance(item, str) else item for item in defs
        ],
    )

    return None


@pytest.mark.parametrize("source_kind", ["file", "directory"])
def test_recipe_compile_implicit_local_source_preserves_options(
    tmp_path, local_registry, source_kind
):
    """Relative shorthand is anchored to recipe_dir and keeps local hooks/args."""
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir()
    data_dir = recipe_dir / "data"
    data_dir.mkdir()
    source = data_dir / "survey.xyz" if source_kind == "file" else data_dir
    if source_kind == "file":
        source.write_text("0 0 1\n", encoding="utf-8")

    # Include both a bare shorthand and a dictionary shorthand. Explicit args
    # and hooks on the dictionary must survive normalization.
    rel_path = "data/survey.xyz" if source_kind == "file" else "data"
    recipe = Recipe(
        {
            "modules": [
                rel_path,
                {
                    "module": rel_path,
                    "args": {"ext": ".xyz"},
                    "hooks": [{"name": "local-hook", "args": {"marker": "kept"}}],
                },
            ]
        },
        base_dir=recipe_dir,
    )

    assert source.exists()
    assert recipe.recipe_dir == recipe_dir

    plan = recipe.compile()
    assert len(plan.modules) == 2
    assert all(isinstance(module, LocalSource) for module in plan.modules)
    assert all(Path(module.path) == source.resolve() for module in plan.modules)
    assert plan.modules[1].ext == ".xyz"
    assert len(plan.modules[1].hook) == 1
    assert isinstance(plan.modules[1].hook[0], LocalHook)
    assert plan.modules[1].hook[0].marker == "kept"
    # Compilation must not mutate the original recipe definition.
    assert recipe.config["modules"][0] == rel_path
    assert recipe.config["modules"][1]["module"] == rel_path


def test_recipe_compile_registered_name_precedes_file_and_missing_path_errors(
    tmp_path, local_registry
):
    """Existing same-named files cannot shadow modules; typos never become local_fs."""
    (tmp_path / "named-source").write_text("collision", encoding="utf-8")

    recipe = Recipe({"modules": ["named-source"]}, base_dir=tmp_path)
    plan = recipe.compile()
    assert len(plan.modules) == 1

    assert isinstance(plan.modules[0], NamedSource)

    for unknown in ("not-a-module", "missing.xyz"):
        recipe = Recipe({"modules": [unknown]}, base_dir=tmp_path)
        with pytest.raises(
            (ValueError, FileNotFoundError),
            match="(?i)(unknown|missing|not found|module|path)",
        ):
            recipe.compile()
