# Tests for declarative and runtime Recipe configurations.

import json
from pathlib import Path
from queue import Queue
from unittest.mock import patch

import pytest

from fetchez.hooks import FetchHook
from fetchez.modules import FetchModule
from fetchez.recipe import Recipe, _safe_config_copy, resolve_component


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

    class FakeRegion:
        def __init__(self, name):
            self.name = name
            self.srs = None

        def to_list(self):
            return [self.name]

        def valid_p(self):
            return True

        def format(self, fmt):
            return self.name

    monkeypatch.setattr(
        recipe_module,
        "yield_parsed_regions",
        lambda region: iter(
            [(FakeRegion("tile_a"), "tile_a"), (FakeRegion("tile_b"), "tile_b")]
        ),
    )
    monkeypatch.setattr(
        recipe_module.Region,
        "from_list",
        lambda values: FakeRegion(values[0]) if values else None,
    )
    monkeypatch.setattr(BundleRegistry, "expand_modules", lambda defs, **kw: defs)
    monkeypatch.setattr(PresetRegistry, "expand_hooks", lambda defs, **kw: defs)
    monkeypatch.setattr(recipe_module.Recipe, "to_markdown", lambda *args, **kw: None)
    monkeypatch.setattr(recipe_module.Recipe, "_init_schemas", lambda self, specs: [])
    monkeypatch.setattr(recipe_module.Recipe, "_init_modifiers", lambda self, specs: [])
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
    assert [m.src_region.name for m in fresh] == ["tile_a", "tile_b"]
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
