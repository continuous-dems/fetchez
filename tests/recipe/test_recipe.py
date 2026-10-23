# Tests for declarative and runtime Recipe configurations.

import json
from pathlib import Path
from queue import Queue
from unittest.mock import patch

import pytest

from fetchez.hooks import FetchHook
from fetchez.modules import FetchModule
from fetchez.spatial import Region
from fetchez.recipe import (
    Recipe,
    RecipeContext,
    PipelinePlan,
    _safe_config_copy,
    resolve_component,
)


class RuntimeHook(FetchHook):
    """Unregistered hook fixture with deliberately simple constructor semantics."""

    name = "test-runtime-hook"

    def __init__(self, output="fixed.txt", queue=None):
        self.output = output
        self.queue = queue


class RuntimeModule(FetchModule):
    """Unregistered module fixture tracking each construction and run."""

    name = "test-runtime-module"
    created = []

    def __init__(self, src_region=None, hook=None, dataset="default", outdir=None):
        self.src_region = src_region
        self.hook = hook if hook is not None else []
        self.dataset = dataset
        self.outdir = outdir
        self.results = []
        type(self).created.append(self)

    def run(self):
        self.results.append(self.dataset)
        return self


@pytest.fixture
def runtime_registry(monkeypatch):
    """Make tests independent of plugin discovery and externally installed extensions."""
    from fetchez.registry import HookRegistry, ModuleRegistry

    monkeypatch.setattr(HookRegistry, "load_all", lambda: None)
    monkeypatch.setattr(ModuleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(
        HookRegistry,
        "get_class",
        lambda name: RuntimeHook if name == "registered-test-hook" else None,
    )
    monkeypatch.setattr(
        ModuleRegistry,
        "get_class",
        lambda name: RuntimeModule if name == "registered-test-module" else None,
    )
    return HookRegistry, ModuleRegistry


def test_recipe_initialization(tmp_path):
    """Direct construction is dict-only; file and dict factories are distinct."""
    config = {"project": {"name": "Test Project", "description": "A test recipe"}}
    recipe = Recipe(config)
    assert recipe.name == "Test Project"
    assert recipe.config["project"]["description"] == "A test recipe"

    assert Recipe.from_dict(config).config == config
    assert Recipe.from_file(config).config == config  # Retained compatibility.

    missing = tmp_path / "missing.yaml"
    with pytest.raises(TypeError, match="config dictionary"):
        Recipe(missing)
    with pytest.raises(FileNotFoundError):
        Recipe.from_file(missing)
    with pytest.raises(TypeError, match="dictionary"):
        Recipe.from_dict(str(missing))

    yaml_path = tmp_path / "recipe.yaml"
    yaml_path.write_text("project:\n  name: File Project\n", encoding="utf-8")
    loaded = Recipe.from_file(yaml_path)
    assert loaded.name == "File Project"
    assert Path(loaded.base_dir) == tmp_path
    assert Recipe.from_dict is not Recipe.from_file


def test_get_module_signature():
    recipe = Recipe({})
    assert recipe._get_module_signature("tnm") == "tnm"
    assert recipe._get_module_signature({"module": "tnm"}) == "tnm"
    mod_ned1 = {"module": "tnm", "args": {"datasets": "1", "weight": 1.0}}
    mod_ned3 = {"module": "tnm", "args": {"datasets": "3", "weight": 1.0}}
    assert recipe._get_module_signature(mod_ned1) == "tnm::datasets=1"
    assert recipe._get_module_signature(mod_ned3) == "tnm::datasets=3"
    assert recipe._get_module_signature(mod_ned1) != recipe._get_module_signature(
        mod_ned3
    )


@patch("fetchez.registry.BundleRegistry.get_yaml")
def test_expand_modules_recursive_and_deduplucate(mock_get_bundle):
    mock_get_bundle.return_value = {
        "modules": [
            {"module": "ehydro", "args": {"weight": 1.0}, "hooks": [{"name": "unzip"}]}
        ]
    }
    recipe = Recipe({})
    expanded = recipe._expand_modules(
        [
            {"bundle": "mock_base_bundle"},
            {"module": "ehydro", "args": {"weight": 5.0}},
        ]
    )
    assert len(expanded) == 2
    assert expanded[0]["module"] == "ehydro"
    assert expanded[0]["args"]["weight"] == 1.0
    assert expanded[0]["hooks"][0]["name"] == "unzip"
    assert expanded[1]["module"] == "ehydro"
    assert expanded[1]["args"]["weight"] == 5.0
    assert expanded[1].get("hooks") is None


def test_to_cli_translation():
    config = {
        "region": "-120.0/-119.0/33.0/34.0",
        "region_srs": "EPSG:4326",
        "execution": {"threads": 4},
        "global_hooks": [{"name": "audit", "args": {"file": "log.json"}}],
        "modules": [
            {"module": "copernicus", "args": {"datatype": 3}},
            {
                "bundle": "crm_standard",
                "args": {"weight": 2.0},
                "hooks": [{"name": "pipe"}],
            },
        ],
    }
    cli_str = Recipe(config).to_cli()
    assert "fetchez build" in cli_str
    assert "-R -120.0/-119.0/33.0/34.0" in cli_str
    assert "--region-srs EPSG:4326" in cli_str
    assert "--threads 4" in cli_str
    assert "--global-hook audit:file=log.json" in cli_str
    assert "copernicus --datatype 3" in cli_str
    assert "crm_standard --weight 2.0" in cli_str
    assert "--hook pipe" in cli_str


def test_to_json_translation():
    recipe = Recipe({"project": {"name": "JSON Test"}, "modules": ["tnm"]})
    parsed = json.loads(recipe.to_json())
    assert parsed["project"]["name"] == "JSON Test"
    assert parsed["modules"][0] == "tnm"


def test_recipe_utils():
    resolved_path = Recipe({})._resolve_path("./test")
    assert Path(resolved_path) == Path.cwd() / "test"


def test_resolve_component_supports_unregistered_classes_and_instances(
    runtime_registry,
):
    hooks, modules = runtime_registry
    hook = RuntimeHook()
    module = RuntimeModule(dataset="preconfigured")
    assert resolve_component(RuntimeHook, hooks, FetchHook) is RuntimeHook
    assert resolve_component(hook, hooks, FetchHook) is hook
    assert resolve_component("registered-test-hook", hooks, FetchHook) is RuntimeHook
    assert resolve_component(RuntimeModule, modules, FetchModule) is RuntimeModule
    assert resolve_component(module, modules, FetchModule) is module
    with pytest.raises(ValueError, match="Unknown component"):
        resolve_component("not-registered", hooks, FetchHook)
    with pytest.raises(TypeError):
        resolve_component(RuntimeModule, hooks, FetchHook)


def test_safe_copy_preserves_nested_runtime_identity():
    queue = Queue(maxsize=2)
    hook = RuntimeHook(queue=queue)
    config = {
        "global_hooks": [{"name": RuntimeHook, "args": {"queue": queue}}, hook],
        "modules": [{"module": RuntimeModule, "hooks": [hook]}],
    }
    copied = _safe_config_copy(config)
    assert copied is not config
    assert copied["global_hooks"] is not config["global_hooks"]
    assert copied["global_hooks"][0] is not config["global_hooks"][0]
    assert copied["global_hooks"][0]["args"]["queue"] is queue
    assert copied["global_hooks"][1] is hook
    assert copied["modules"][0]["hooks"][0] is hook
    copied["global_hooks"][0]["args"]["other"] = "new"
    assert "other" not in config["global_hooks"][0]["args"]


def test_runtime_hook_initialization_and_explicit_instance_state(runtime_registry):
    recipe = Recipe({})
    queue = Queue(maxsize=1)
    configured = RuntimeHook(output="literal_%batch_name%.txt", queue=queue)
    hooks = recipe._init_hooks(
        [
            {"name": "registered-test-hook", "args": {"output": "named.txt"}},
            {"name": RuntimeHook, "args": {"output": "class.txt", "queue": queue}},
            RuntimeHook,
            configured,
            {"name": configured},
        ]
    )
    assert [type(h) for h in hooks] == [RuntimeHook] * 5
    assert Path(hooks[0].output).name == "named.txt"
    assert Path(hooks[1].output).name == "class.txt"
    assert hooks[1].queue is queue
    assert hooks[2] is not configured
    assert hooks[3] is configured and hooks[4] is configured
    assert configured.output == "literal_%batch_name%.txt"
    with pytest.raises(ValueError, match="already configured"):
        recipe._init_hooks([{"name": configured, "args": {"output": "override.txt"}}])
    with pytest.raises(TypeError, match="does not accept arguments"):
        recipe._init_hooks([{"name": RuntimeHook, "args": {"typo": True}}])


def test_runtime_module_initialization_and_explicit_instance_state(runtime_registry):
    recipe = Recipe({})
    configured_hook = RuntimeHook(output="as-is.txt")
    configured = RuntimeModule(
        dataset="configured", hook=[configured_hook], src_region="fixed"
    )
    modules = recipe._init_modules(
        [
            {"module": "registered-test-module", "args": {"dataset": "registered"}},
            {
                "module": RuntimeModule,
                "args": {"dataset": "class"},
                "hooks": [RuntimeHook],
            },
            configured,
        ]
    )
    assert modules[0].dataset == "registered"
    assert modules[1].dataset == "class"
    assert isinstance(modules[1].hook[0], RuntimeHook)
    assert modules[2] is configured
    assert configured.src_region == "fixed"
    assert configured.hook == [configured_hook]
    with pytest.raises(ValueError, match="already configured"):
        recipe._init_modules([{"module": configured, "args": {"dataset": "override"}}])
    with pytest.raises(TypeError, match="does not accept arguments"):
        recipe._init_modules([{"module": RuntimeModule, "args": {"typo": True}}])


def test_mixed_expansion_keeps_runtime_positions_and_instances(monkeypatch):
    from fetchez.registry import BundleRegistry, PresetRegistry

    original_hook = RuntimeHook(output="persist.txt")
    original_module = RuntimeModule(dataset="persist")
    hook_calls, module_calls = [], []

    def expand_hooks(defs, **kwargs):
        hook_calls.append(list(defs))
        return [{"name": "expanded-hook"} for _ in defs]

    def expand_modules(defs, **kwargs):
        module_calls.append(list(defs))
        return [{"module": "expanded-module"} for _ in defs]

    monkeypatch.setattr(PresetRegistry, "expand_hooks", expand_hooks)
    monkeypatch.setattr(BundleRegistry, "expand_modules", expand_modules)
    recipe = Recipe({})
    hooks = recipe._expand_hooks(
        [{"preset": "a"}, original_hook, {"name": RuntimeHook}, {"preset": "b"}]
    )
    modules = recipe._expand_modules(
        [{"bundle": "a"}, original_module, {"module": RuntimeModule}, {"bundle": "b"}]
    )
    assert hooks == [
        {"name": "expanded-hook"},
        original_hook,
        {"name": RuntimeHook},
        {"name": "expanded-hook"},
    ]
    assert modules == [
        {"module": "expanded-module"},
        original_module,
        {"module": RuntimeModule},
        {"module": "expanded-module"},
    ]
    assert hooks[1] is original_hook
    assert modules[1] is original_module
    assert len(hook_calls) == len(module_calls) == 2


@pytest.mark.parametrize("runtime_component", [RuntimeHook, RuntimeHook()])
def test_runtime_hook_recipes_reject_cli_and_json(runtime_component):
    recipe = Recipe.from_dict({"global_hooks": [runtime_component]})
    with pytest.raises(TypeError, match="runtime components"):
        recipe.to_cli()
    with pytest.raises(TypeError, match="runtime components"):
        recipe.to_json()


def test_runtime_module_recipes_reject_cli_and_json():
    recipe = Recipe.from_dict({"modules": [{"module": RuntimeModule}]})
    with pytest.raises(TypeError, match="runtime components"):
        recipe.to_cli()
    with pytest.raises(TypeError, match="runtime components"):
        recipe.to_json()


def test_runtime_batch_context_instantiates_classes_but_preserves_instances(
    tmp_path, monkeypatch, runtime_registry
):
    """Exercise expansion, interpolation, receipt, and execution across two batches."""
    import fetchez.recipe as recipe_module
    from fetchez.registry import BundleRegistry, PresetRegistry

    # Only stub batch enumeration. Region parsing inside compile() stays real.
    original_parser = recipe_module.yield_parsed_regions
    batches = [
        (Region(-120.0, -119.75, 33.0, 33.25, srs="EPSG:4326"), "tile_a"),
        (Region(-119.75, -119.5, 33.0, 33.25, srs="EPSG:4326"), "tile_b"),
    ]

    def parsed_regions(value):
        if value == "ignored-by-mock":
            return iter(batches)
        return original_parser(value)

    monkeypatch.setattr(recipe_module, "yield_parsed_regions", parsed_regions)
    monkeypatch.setattr(BundleRegistry, "expand_modules", lambda defs, **kw: defs)
    monkeypatch.setattr(PresetRegistry, "expand_hooks", lambda defs, **kw: defs)
    monkeypatch.setattr(recipe_module.Recipe, "to_markdown", lambda *args, **kw: None)
    monkeypatch.setattr(
        recipe_module.Recipe, "_init_schemas", lambda self, specs, **kwargs: []
    )
    monkeypatch.setattr(
        recipe_module.Recipe, "_init_modifiers", lambda self, specs, **kwargs: []
    )
    executed = []
    monkeypatch.setattr(
        recipe_module,
        "run_fetchez",
        lambda modules, **kw: executed.append(
            (list(modules), list(kw["global_hooks"]))
        ),
    )
    monkeypatch.setattr(recipe_module.tracemalloc, "start", lambda: None)
    monkeypatch.setattr(recipe_module.tracemalloc, "stop", lambda: None)
    monkeypatch.setattr(recipe_module.tracemalloc, "get_traced_memory", lambda: (0, 0))

    queue = Queue(maxsize=2)
    live_hook = RuntimeHook(output="unchanged_%batch_name%.txt", queue=queue)
    live_module = RuntimeModule(dataset="persistent", src_region="original")
    RuntimeModule.created.clear()
    recipe = Recipe.from_dict(
        {
            "project": {"name": "runtime-test"},
            "region": "ignored-by-mock",
            "modules": [
                {"module": RuntimeModule, "args": {"dataset": "%batch_name%"}},
                live_module,
            ],
            "global_hooks": [
                {"name": RuntimeHook, "args": {"output": "%name%_%batch_name%.txt"}},
                live_hook,
            ],
        }
    )

    receipts = list(recipe.run(outdir=tmp_path))
    assert len(receipts) == 2
    assert [r[2] for r in receipts] == ["tile_a", "tile_b"]
    fresh = [m for m in RuntimeModule.created if m is not live_module]
    assert len(fresh) == 2
    assert fresh[0] is not fresh[1]
    assert [m.dataset for m in fresh] == ["tile_a", "tile_b"]
    assert [m.src_region.to_list() for m in fresh] == [r.to_list() for r, _ in batches]
    assert live_module.src_region == "original"
    assert live_module.results == ["persistent", "persistent"]
    assert live_hook.output == "unchanged_%batch_name%.txt"
    assert live_hook.queue is queue
    assert len(executed) == 2
    assert executed[0][0][1] is live_module and executed[1][0][1] is live_module
    assert executed[0][1][1] is live_hook and executed[1][1][1] is live_hook
    assert executed[0][1][0] is not executed[1][1][0]
    assert Path(executed[0][1][0].output).name == "runtime-test_tile_a.txt"
    assert Path(executed[1][1][0].output).name == "runtime-test_tile_b.txt"


# ---------------------------------------------------------------------------
# Recipe.compile() / PipelinePlan regression tests (post-refactor)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_compiler(monkeypatch, runtime_registry):
    """Exercise actual compilation without plugin discovery or unrelated schemas."""
    from fetchez.registry import (
        BundleRegistry,
        PresetRegistry,
        ModifierRegistry,
        SchemaRegistry,
    )

    for registry in (BundleRegistry, PresetRegistry, ModifierRegistry, SchemaRegistry):
        monkeypatch.setattr(registry, "load_all", lambda: None)

    monkeypatch.setattr(BundleRegistry, "expand_modules", lambda specs, **kw: specs)
    monkeypatch.setattr(PresetRegistry, "expand_hooks", lambda specs, **kw: specs)
    monkeypatch.setattr(Recipe, "_init_modifiers", lambda self, specs, **kw: [])
    monkeypatch.setattr(Recipe, "_init_schemas", lambda self, specs: [])


class PlanRegion:
    """Minimal Region double for predictable, network-free compilation tests."""

    def __init__(self, name, srs=None):
        self.name = name
        self.srs = srs

    def to_list(self):
        return [self.name]

    def valid_p(self):
        return True

    def format(self, fmt):
        assert fmt == "fn"
        return self.name


@pytest.fixture
def plan_regions():
    """Compatibility fixture: compilation now uses real, parseable regions."""
    return Region


def sample_region(index=0):
    """Valid bounds, varying per batch without relying on fake parsers."""
    west = -120.0 + 0.25 * index
    return Region(west, west + 0.25, 33.0, 33.25, srs="EPSG:4326")


def test_recipe_context_placeholders_are_explicit_and_batch_aware(tmp_path):
    ctx = RecipeContext(
        region=PlanRegion("n33w120"),
        region_srs="EPSG:4326",
        name="coastal",
        outdir=tmp_path,
        tile_dir=tmp_path / "tile_a",
        shared_cache=tmp_path / "cache",
    )
    assert ctx.placeholders()["batch_name"] == "n33w120"
    assert ctx.placeholders()["name"] == "coastal"
    assert ctx.placeholders()["outdir"] == tmp_path
    assert ctx.placeholders()["tile_dir"] == tmp_path / "tile_a"
    assert ctx.placeholders()["cache_dir"] == tmp_path / "cache"

    named = RecipeContext(region=PlanRegion("fallback"), batch_name="actual_tile")
    assert named.placeholders()["batch_name"] == "actual_tile"


def test_compile_is_preparation_only_and_preserves_caller_state(
    tmp_path, monkeypatch, isolated_compiler, plan_regions
):
    """compile() must not execute, change cwd, or create batch/receipt files."""
    import fetchez.recipe as recipe_module

    monkeypatch.setattr(
        recipe_module,
        "run_fetchez",
        lambda *args, **kwargs: pytest.fail("compile() executed the pipeline"),
    )
    RuntimeModule.created.clear()
    ctx = RecipeContext(
        region=sample_region(),
        name="compiler-test",
        batch_name="tile_a",
        tile_dir=tmp_path / "not-created",
        outdir=tmp_path,
    )
    config = {
        "project": {"name": "compiler-test"},
        "modules": [{"module": RuntimeModule, "args": {"dataset": "%batch_name%"}}],
        "global_hooks": [
            {"name": RuntimeHook, "args": {"output": "%tile_dir%/result.tif"}}
        ],
        "execution": {"threads": 3},
    }
    recipe = Recipe.from_dict(config)
    cwd_before = Path.cwd()
    plan = recipe.compile(ctx)

    assert isinstance(plan, PipelinePlan)
    assert Path.cwd() == cwd_before
    assert not ctx.tile_dir.exists()
    assert not list(tmp_path.glob("**/*receipt.md"))
    assert plan.threads == 3
    assert plan.region is not ctx.region
    assert plan.region.to_list() == ctx.region.to_list()
    assert plan.region.srs == ctx.region_srs
    assert plan.modules[0].src_region.to_list() == ctx.region.to_list()
    assert plan.batch_name == "tile_a"
    assert plan.modules[0].results == []  # module.run() was not called
    assert plan.modules[0].dataset == "tile_a"
    assert Path(plan.global_hooks[0].output) == ctx.tile_dir / "result.tif"
    assert recipe.config == config
    assert recipe.config["modules"][0]["args"]["dataset"] == "%batch_name%"


class WidenRegion:
    """Modifier double that widens config["region"], like globato's buffer-and-cut."""

    def __init__(self, by):
        self.by = by

    def apply(self, config):
        w, e, s, n = config["region"]
        config["region"] = [w - self.by, e + self.by, s - self.by, n + self.by]
        return config


def _region_modifier_plan(tmp_path, monkeypatch, by):
    from fetchez.spatial import Region

    monkeypatch.setattr(
        Recipe, "_init_modifiers", lambda self, specs, **kw: [WidenRegion(by)]
    )
    ctx = RecipeContext(
        region=Region(-123.5, -123.25, 36.0, 36.25, srs="EPSG:4326"),
        name="buffered",
        batch_name="tile_a",
        tile_dir=tmp_path / "tile_a",
        outdir=tmp_path,
    )
    config = {
        "project": {"name": "buffered"},
        "modifiers": [{"name": "widen"}],
        "modules": [{"module": RuntimeModule, "args": {"dataset": "%batch_name%"}}],
        "global_hooks": [
            {"name": RuntimeHook, "args": {"output": "%name%_%batch_name%.tif"}}
        ],
    }
    return ctx, Recipe.from_dict(config).compile(ctx)


def test_compile_builds_on_the_region_a_modifier_sets(
    tmp_path, monkeypatch, isolated_compiler
):
    """A modifier's region change reaches the modules and plan; naming keeps the batch."""
    ctx, plan = _region_modifier_plan(tmp_path, monkeypatch, by=0.05)

    widened = [-123.55, -123.2, 35.95, 36.3]
    assert plan.config["region"] == pytest.approx(widened)
    assert plan.region.to_list() == pytest.approx(widened)
    assert plan.region.srs == "EPSG:4326"
    assert plan.modules[0].src_region.to_list() == pytest.approx(widened)
    assert ctx.region.to_list() == [-123.5, -123.25, 36.0, 36.25]
    assert plan.batch_name == "tile_a"
    assert plan.modules[0].dataset == "tile_a"
    assert plan.global_hooks[0].output.endswith("buffered_tile_a.tif")


def test_compile_keeps_the_batch_region_when_no_modifier_changes_it(
    tmp_path, monkeypatch, isolated_compiler
):
    ctx, plan = _region_modifier_plan(tmp_path, monkeypatch, by=0.0)

    assert plan.region is not ctx.region
    assert plan.region.to_list() == ctx.region.to_list()
    assert plan.region.srs == ctx.region_srs
    assert plan.modules[0].src_region.to_list() == ctx.region.to_list()


def test_compile_creates_fresh_classes_and_preserves_supplied_instances(
    tmp_path, isolated_compiler, plan_regions
):
    queue = Queue()
    instance_hook = RuntimeHook(output="do_not_expand_%batch_name%", queue=queue)
    instance_module = RuntimeModule(dataset="keep", src_region="untouched")
    recipe = Recipe.from_dict(
        {
            "modules": [
                {"module": RuntimeModule, "args": {"dataset": "%batch_name%"}},
                instance_module,
            ],
            "global_hooks": [
                {"name": RuntimeHook, "args": {"output": "result_%batch_name%.tif"}},
                instance_hook,
            ],
        }
    )
    first = recipe.compile(
        RecipeContext(region=sample_region(0), batch_name="a", tile_dir=tmp_path)
    )
    second = recipe.compile(
        RecipeContext(region=sample_region(1), batch_name="b", tile_dir=tmp_path)
    )

    assert first.modules[0] is not second.modules[0]
    assert first.modules[0].dataset == "a"
    assert second.modules[0].dataset == "b"
    assert first.global_hooks[0] is not second.global_hooks[0]
    assert Path(first.global_hooks[0].output).name == "result_a.tif"
    assert Path(second.global_hooks[0].output).name == "result_b.tif"
    assert first.modules[1] is second.modules[1] is instance_module
    assert first.global_hooks[1] is second.global_hooks[1] is instance_hook
    assert instance_module.src_region == "untouched"
    assert instance_hook.output == "do_not_expand_%batch_name%"
    assert instance_hook.queue is queue


def test_compile_resolves_global_and_module_hook_outputs_relative_to_tile(
    tmp_path, isolated_compiler, plan_regions
):
    recipe_dir = tmp_path / "recipes"
    tile_dir = tmp_path / "output" / "tile_01"
    recipe = Recipe(
        {
            "modules": [
                {
                    "module": RuntimeModule,
                    "hooks": [{"name": RuntimeHook, "args": {"output": "local.tif"}}],
                }
            ],
            "global_hooks": [{"name": RuntimeHook, "args": {"output": "global.tif"}}],
        },
        base_dir=recipe_dir,
    )
    plan = recipe.compile(RecipeContext(region=sample_region(), tile_dir=tile_dir))

    assert Path(plan.global_hooks[0].output) == tile_dir / "global.tif"
    assert Path(plan.modules[0].hook[0].output) == tile_dir / "local.tif"
    assert not tile_dir.exists()  # Path resolution must not mkdir


def test_legacy_path_rules_only_touch_known_keys(tmp_path):
    recipe = Recipe({}, base_dir=tmp_path / "recipe-dir")
    args = {
        "file": "input.tif",
        "output": "output.tif",
        "custom_path": "untouched.tif",
        "barrier": 123,
        "url": "https://example.org/data.tif",
    }
    resolved = recipe._resolve_args_paths(
        args,
        input_keys={"file", "barrier"},
        output_keys={"output"},
        input_dir=tmp_path / "recipe-dir",
        output_dir=tmp_path / "tile-dir",
    )
    assert Path(resolved["file"]) == tmp_path / "recipe-dir" / "input.tif"
    assert Path(resolved["output"]) == tmp_path / "tile-dir" / "output.tif"
    assert resolved["custom_path"] == "untouched.tif"
    assert resolved["barrier"] == 123
    assert resolved["url"] == args["url"]
    assert args["file"] == "input.tif"  # Never mutate caller's arguments
    assert recipe._resolve_path("s3://bucket/data.tif") == "s3://bucket/data.tif"


def test_compile_applies_refresh_and_cache_only_to_declarative_classes(
    tmp_path, isolated_compiler, plan_regions
):
    """Existing runtime instances remain untouched by execution overrides."""
    original = RuntimeModule(dataset="already-configured", outdir="as-provided")

    class CacheAwareModule(RuntimeModule):
        def __init__(self, src_region=None, hook=None, outdir=None, use_cache=True):
            super().__init__(src_region=src_region, hook=hook, outdir=outdir)
            self.use_cache = use_cache

    recipe = Recipe(
        {
            "modules": [{"module": CacheAwareModule}, original],
        }
    )
    cache = tmp_path / "cache"
    plan = recipe.compile(
        RecipeContext(
            region=sample_region(),
            shared_cache=cache,
            refresh=True,
        )
    )
    assert plan.modules[0].use_cache is False
    assert Path(plan.modules[0].outdir) == cache
    assert plan.modules[1] is original
    assert original.outdir == "as-provided"


def test_plan_execute_runs_each_module_and_engine_once(monkeypatch):
    import fetchez.recipe as recipe_module

    calls = []

    class RunningModule(RuntimeModule):
        def run(self):
            calls.append(("module", self.dataset))
            return self

    def engine(modules, **kwargs):
        calls.append(("engine", len(modules)))
        assert kwargs["threads"] == 5
        assert kwargs["global_hooks"] == ["existing"]
        return ["result"]

    monkeypatch.setattr(recipe_module, "run_fetchez", engine)
    plan = PipelinePlan(
        config={"execution": {"threads": 5}},
        modules=[RunningModule(dataset="a"), RunningModule(dataset="b")],
        global_hooks=["existing"],
    )
    result = plan.execute()
    assert calls == [("module", "a"), ("module", "b"), ("engine", 2)]
    assert result == ["result"]


def test_plan_execute_failure_preserves_exception_and_stops_tracing(monkeypatch):
    import fetchez.recipe as recipe_module

    failure = RuntimeError("engine failed")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(recipe_module, "run_fetchez", fail)
    plan = PipelinePlan(config={}, modules=[], global_hooks=[])
    with pytest.raises(RuntimeError, match="engine failed") as caught:
        plan.execute()
    assert caught.value is failure
    assert not recipe_module.tracemalloc.is_tracing()


def test_recipe_run_yields_with_restored_cwd_and_resumes(
    tmp_path, monkeypatch, isolated_compiler, plan_regions
):
    import fetchez.recipe as recipe_module

    original = Path.cwd()
    original_parser = recipe_module.yield_parsed_regions
    batches = [(sample_region(0), "tile_a"), (sample_region(1), "tile_b")]

    def parsed_regions(raw):
        if raw == "fake":
            return iter(batches)
        return original_parser(raw)

    monkeypatch.setattr(recipe_module, "yield_parsed_regions", parsed_regions)
    monkeypatch.setattr(recipe_module.Recipe, "to_markdown", lambda *a, **kw: None)
    monkeypatch.setattr(recipe_module, "run_fetchez", lambda *a, **kw: [])

    recipe = Recipe(
        {"project": {"name": "test"}, "region": "fake", "modules": [RuntimeModule]}
    )
    iterator = recipe.run(outdir=tmp_path)
    first = next(iterator)
    assert first[2] == "tile_a"
    assert first[1].to_list() == batches[0][0].to_list()
    assert Path.cwd() == original  # CWD restored even while generator suspended
    assert (tmp_path / "tile_a").is_dir()
    assert json.loads((tmp_path / "fetchez_batch_state.json").read_text()) == ["tile_a"]
    remaining = list(iterator)
    assert [batch[2] for batch in remaining] == ["tile_b"]
    assert Path.cwd() == original
    assert json.loads((tmp_path / "fetchez_batch_state.json").read_text()) == [
        "tile_a",
        "tile_b",
    ]

    assert list(recipe.run(outdir=tmp_path)) == []
    assert Path.cwd() == original


def test_compile_without_context_uses_unambiguous_recipe_region(
    monkeypatch, isolated_compiler, plan_regions
):

    recipe = Recipe({"region": sample_region().to_list(), "modules": [RuntimeModule]})
    plan = recipe.compile()
    assert plan.region is not None
    assert plan.region.to_list() == sample_region().to_list()
    assert plan.modules[0].src_region.to_list() == sample_region().to_list()


def test_compile_without_context_rejects_ambiguous_batches(
    monkeypatch, isolated_compiler
):
    import fetchez.recipe as recipe_module

    monkeypatch.setattr(
        recipe_module,
        "yield_parsed_regions",
        lambda raw: iter([(PlanRegion("a"), "a"), (PlanRegion("b"), "b")]),
    )
    recipe = Recipe({"region": "many", "modules": [RuntimeModule]})
    with pytest.raises(ValueError, match="context|multiple|region|batch"):
        recipe.compile()


def test_compile_without_region_keeps_global_scope(isolated_compiler):
    """A recipe without a region must remain a valid global workflow."""
    recipe = Recipe({"modules": [RuntimeModule]})
    plan = recipe.compile()
    assert plan.region is None
    assert plan.modules[0].src_region is None


def test_modifier_execution_threads_are_taken_from_final_config(
    tmp_path, monkeypatch, isolated_compiler
):
    """Modifiers must be able to change execution options consumed by the plan."""

    class ChangeThreads:
        def apply(self, config):
            config.setdefault("execution", {})["threads"] = 7
            return config

    monkeypatch.setattr(
        Recipe, "_init_modifiers", lambda self, specs, **kw: [ChangeThreads()]
    )
    recipe = Recipe(
        {
            "modules": [RuntimeModule],
            "execution": {"threads": 2},
            "modifiers": [{"name": "change-threads"}],
        }
    )
    plan = recipe.compile(RecipeContext(region=sample_region(), tile_dir=tmp_path))
    assert plan.config["execution"]["threads"] == 7
    assert plan.threads == 7
    assert recipe.config["execution"]["threads"] == 2
