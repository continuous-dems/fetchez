"""Offline contract/resilience tests for fetchez.recipe.

Known/suspected defects are strict xfails. Remove each marker after fixing
its underlying contract; an XPASS then signals the test should be promoted.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

import fetchez.recipe as recipe_module
from fetchez.hooks import FetchHook
from fetchez.modules import FetchModule
from fetchez.recipe import (
    PipelinePlan,
    Recipe,
    RecipeContext,
    _parse_version,
    _safe_config_copy,
    resolve_module_reference,
)
from fetchez.registry import (
    BundleRegistry,
    HookRegistry,
    ModifierRegistry,
    ModuleRegistry,
    PresetRegistry,
    SchemaRegistry,
)


class SampleHook(FetchHook):
    name = "resilience-hook"

    def __init__(self, output=None, file=None, marker=None):
        self.output = output
        self.file = file
        self.marker = marker


class SampleModule(FetchModule):
    name = "resilience-module"

    def __init__(
        self,
        src_region=None,
        hook=None,
        path=None,
        outdir=None,
        use_cache=True,
        dataset=None,
    ):
        self.src_region = src_region
        self.hook = [] if hook is None else hook
        self.path = path
        self.outdir = outdir
        self.use_cache = use_cache
        self.dataset = dataset
        self.calls = 0

    def run(self):
        self.calls += 1
        return self


@pytest.fixture
def isolated_recipe(monkeypatch):
    """Compile with real Recipe logic, but no installed plugins or network."""
    for registry in (
        ModuleRegistry,
        HookRegistry,
        BundleRegistry,
        PresetRegistry,
        ModifierRegistry,
        SchemaRegistry,
    ):
        monkeypatch.setattr(registry, "load_all", lambda: {})

    monkeypatch.setattr(
        ModuleRegistry,
        "get_class",
        lambda name: {"resilience-module": SampleModule, "local_fs": SampleModule}.get(
            name
        ),
    )
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        lambda name: {"resilience-hook": SampleHook}.get(name),
    )
    monkeypatch.setattr(
        BundleRegistry,
        "expand_modules",
        lambda items, **kwargs: [
            {"module": item} if isinstance(item, str) else item for item in items
        ],
    )
    monkeypatch.setattr(
        PresetRegistry, "expand_hooks", lambda items, **kwargs: list(items)
    )
    monkeypatch.setattr(Recipe, "_init_schemas", lambda self, defs: [])
    monkeypatch.setattr(Recipe, "_init_modifiers", lambda self, defs, **kwargs: [])


def test_compile_is_repeatable_with_nested_mutable_args(isolated_recipe, tmp_path):
    """Compilation must not write runtime defaults into the original definition."""
    config = {
        "project": {"name": "repeat"},
        "modules": [{"module": SampleModule, "args": {"dataset": "tile_%batch_name%"}}],
        "global_hooks": [{"name": SampleHook, "args": {"marker": ["a", "b"]}}],
    }
    recipe = Recipe.from_dict(config)
    a = recipe.compile(RecipeContext(batch_name="a", tile_dir=tmp_path / "a"))
    b = recipe.compile(RecipeContext(batch_name="b", tile_dir=tmp_path / "b"))
    assert a.modules[0] is not b.modules[0]
    assert a.modules[0].dataset == "tile_a"
    assert b.modules[0].dataset == "tile_b"
    assert a.global_hooks[0].marker == ["a", "b"]
    assert b.global_hooks[0].marker == ["a", "b"]
    assert config["modules"][0]["args"]["dataset"] == "tile_%batch_name%"
    assert "hook" not in config["modules"][0]
    assert config["project"]["name"] == "repeat"


def test_compile_runtime_instance_rejects_extra_configuration(isolated_recipe):
    """Instances are already configured and cannot be overridden incidentally."""
    hook = SampleHook(marker="original")
    module = SampleModule(dataset="original")
    with pytest.raises(ValueError, match="already configured"):
        Recipe({"global_hooks": [{"name": hook, "args": {"marker": "new"}}]}).compile()
    with pytest.raises(ValueError, match="already configured"):
        Recipe({"modules": [{"module": module, "hooks": [SampleHook]}]}).compile()
    assert hook.marker == "original"
    assert module.dataset == "original"


def test_module_reference_registered_name_precedes_existing_file(
    isolated_recipe, tmp_path
):
    (tmp_path / "resilience-module").write_text("data", encoding="utf-8")
    resolved, kwargs = resolve_module_reference("resilience-module", base_dir=tmp_path)
    assert resolved is SampleModule
    assert kwargs == {}


def test_module_reference_local_file_and_missing_path(isolated_recipe, tmp_path):
    source = tmp_path / "survey.xyz"
    source.write_text("1 2 3\n", encoding="utf-8")
    resolved, kwargs = resolve_module_reference("survey.xyz", base_dir=tmp_path)
    assert resolved is SampleModule
    assert Path(kwargs["path"]) == source.resolve()
    with pytest.raises(ValueError, match="Unknown module"):
        resolve_module_reference("does_not_exist.xyz", base_dir=tmp_path)


def test_context_placeholder_fallback_and_explicit_batch(tmp_path):
    context = RecipeContext(name="demo", tile_dir=tmp_path / "tile")
    values = context.placeholders()
    assert values["name"] == "demo"
    assert values["batch_name"] == ""
    assert values["shared_cache"] == tmp_path / "tile"
    assert values["cache_dir"] == tmp_path / "tile"
    explicit = RecipeContext(batch_name="my_batch", shared_cache=tmp_path / "shared")
    assert explicit.placeholders()["batch_name"] == "my_batch"
    assert explicit.placeholders()["cache_dir"] == tmp_path / "shared"


def test_nested_placeholder_replacement_leaves_unknown_tokens_unchanged():
    recipe = Recipe({})
    original = {"modules": [{"args": {"nested": ["%name%", "%unknown%"]}}]}
    result = recipe._inject_batch_context(original, name="demo")
    assert result == {"modules": [{"args": {"nested": ["demo", "%unknown%"]}}]}
    assert original["modules"][0]["args"]["nested"][0] == "%name%"


def test_safe_copy_keeps_runtime_objects_and_copies_containers():
    sentinel = object()
    value = {"items": [{"object": sentinel, "paths": [Path("a")]}]}
    copied = _safe_config_copy(value)
    assert copied is not value
    assert copied["items"] is not value["items"]
    assert copied["items"][0] is not value["items"][0]
    assert copied["items"][0]["object"] is sentinel
    assert copied["items"][0]["paths"] == [Path("a")]


def test_refresh_and_cache_are_per_compile_not_caller_mutations(
    isolated_recipe, tmp_path
):
    config = {"modules": [{"module": SampleModule}]}
    recipe = Recipe(config)
    cached = recipe.compile(
        RecipeContext(shared_cache=tmp_path / "cache", refresh=True)
    )
    normal = recipe.compile(RecipeContext())
    assert cached.modules[0].use_cache is False
    assert Path(cached.modules[0].outdir) == tmp_path / "cache"
    assert normal.modules[0].use_cache is True
    assert normal.modules[0].outdir is None
    assert config == {"modules": [{"module": SampleModule}]}


def test_plan_discovery_failure_strict_does_not_invoke_engine(monkeypatch):
    module = SampleModule()
    module.run = Mock(side_effect=RuntimeError("discovery failure"))
    engine = Mock()
    monkeypatch.setattr(recipe_module, "run_fetchez", engine)
    plan = PipelinePlan(config={}, modules=[module], global_hooks=[])
    with pytest.raises(RuntimeError, match="discovery failure"):
        plan.execute()
    engine.assert_not_called()


def test_plan_discovery_failure_tolerant_continues_to_engine(monkeypatch):
    broken = SampleModule(dataset="broken")
    broken.run = Mock(side_effect=RuntimeError("discovery failure"))
    good = SampleModule(dataset="good")
    engine = Mock(return_value=["finished"])
    monkeypatch.setattr(recipe_module, "run_fetchez", engine)
    plan = PipelinePlan(
        config={}, modules=[broken, good], global_hooks=[], ignore_failures=True
    )
    assert plan.execute() == ["finished"]
    broken.run.assert_called_once()
    assert good.calls == 1
    engine.assert_called_once()
    assert engine.call_args.kwargs["ignore_failures"] is True


def test_version_prerelease_suffix_does_not_change_patch_number():
    assert _parse_version("1.2.3rc4") == (1, 2, 3, 4)


def test_explicit_schema_rejection_prevents_compilation(isolated_recipe, monkeypatch):
    class RejectingSchema:
        name = "rejecting-schema"

        def run(self, config):
            return False, ["invalid options"]

    monkeypatch.setattr(Recipe, "_init_schemas", lambda self, defs: [RejectingSchema()])
    with pytest.raises(ValueError, match="invalid options"):
        Recipe({"schemas": [{"name": "rejecting-schema"}]}).compile()


def test_modifier_constructor_typo_raises_instead_of_disappearing(monkeypatch):
    class DummyModifier:
        def __init__(self, threshold=1):
            self.threshold = threshold

    monkeypatch.setattr(ModifierRegistry, "load_all", lambda: {})
    monkeypatch.setattr(
        ModifierRegistry,
        "get_class",
        lambda name: DummyModifier if name == "dummy" else None,
    )
    with pytest.raises(TypeError, match="typo"):
        Recipe({})._init_modifiers([{"name": "dummy", "args": {"typo": 1}}])


@pytest.mark.parametrize("ignore_failures", [False, True])
def test_schema_failure_policy(ignore_failures, monkeypatch):
    recipe = Recipe({"project": {"name": "schema-test"}})

    monkeypatch.setattr(
        recipe,
        "_validate_config",
        lambda config: ["Invalid test configuration"],
    )

    # Other compilation dependencies can be isolated as in
    # the existing recipe resilience fixtures.

    if ignore_failures:
        plan = recipe.compile(ignore_failures=True)
        assert plan.ignore_failures is True
    else:
        with pytest.raises(ValueError, match="Invalid test configuration"):
            recipe.compile(ignore_failures=False)
