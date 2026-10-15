#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.recipe
~~~~~~~~~~~~~~

The Recipe Engine.
Loads a configuration (The Recipe) and executes it against the target region.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import json
import yaml

import inspect
import logging
import tracemalloc
from pathlib import Path

from .core import run_fetchez
from .spatial import yield_parsed_regions, Region
from .registry import (
    ModuleRegistry,
    HookRegistry,
    ModifierRegistry,
    SchemaRegistry,
    PresetRegistry,
    BundleRegistry,
    RecipeRegistry,
)
from fetchez.hooks import FetchHook
from fetchez.modules import FetchModule
from .utils import colorize, CYAN
from . import __version__ as fetchez_version

from typing import Any, Optional

logger = logging.getLogger(__name__)


def _parse_version(v_str):
    """Dependency-free semantic version parser.
    Converts '2.1.0-beta' into (2, 1, 0).
    """

    parts = []
    for p in v_str.split("."):
        num = "".join(filter(str.isdigit, p))
        parts.append(int(num) if num else 0)
    return tuple(parts)


def load_recipe_config(target):
    base_config = None
    target_path = Path(target)
    if target_path.exists() and not target_path.is_dir():
        with open(target, "r", encoding="utf-8") as f:
            base_config = yaml.safe_load(f)
    else:
        RecipeRegistry.load_all()
        recipe_meta = RecipeRegistry.get_yaml(target)
        if recipe_meta:
            base_config = recipe_meta["config"]
            logger.info(f"Loaded curated recipe: {target}")

    return base_config


def _safe_config_copy(value):
    """Copy configuration containers without cloning runtime objects."""

    if isinstance(value, dict):
        return {_safe_config_copy(k): _safe_config_copy(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_safe_config_copy(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_safe_config_copy(item) for item in value)

    if isinstance(value, (str, int, float, bool, type(None), Path)):
        return value

    # Preserve arbitrary runtime objects by identity.
    return value


def resolve_component(spec, registry, base_class):
    """Resolve a component reference without instantiating it."""

    if isinstance(spec, base_class):
        return spec

    if inspect.isclass(spec):
        if not issubclass(spec, base_class):
            raise TypeError(f"{spec} must subclass {base_class.__name__}")
        return spec

    if isinstance(spec, str):
        registry.load_all()
        cls = registry.get_class(spec)
        if cls is None:
            raise ValueError(f"Unknown component: {spec}")
        return cls

    raise TypeError(f"Unsupported component: {spec!r}")


def _runtime_definition(value, kind):
    """Whether a definition contains a Python component that registries cannot expand."""
    base = FetchHook if kind == "hook" else FetchModule
    if isinstance(value, base) or inspect.isclass(value):
        return True
    if not isinstance(value, dict):
        return False
    ref = value.get("name" if kind == "hook" else "module")
    return (
        isinstance(ref, base)
        or inspect.isclass(ref)
        or (
            kind == "module"
            and any(
                _runtime_definition(hook, "hook") for hook in value.get("hooks", [])
            )
        )
    )


def _component_label(value):
    """Human-readable component name without serializing its live state."""
    if isinstance(value, str):
        return value
    if inspect.isclass(value):
        return value.__name__
    return getattr(value, "name", type(value).__name__)


def _constructor_kwargs(cls, kwargs):
    """Validate constructor options without silently dropping misspelled keys."""
    sig = inspect.signature(cls.__init__)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    unsupported = set(kwargs) - set(sig.parameters)
    if unsupported:
        raise TypeError(
            f"{cls.__name__} does not accept arguments: {', '.join(sorted(unsupported))}"
        )
    return kwargs


def _expand_declarative_segments(definitions, registry_expand, kind, **kwargs):
    """Expand YAML definitions in runs, retaining Python definitions in order."""
    expanded = []
    declarative = []

    def flush():
        if declarative:
            expanded.extend(registry_expand(declarative, **kwargs))
            declarative.clear()

    for item in definitions:
        if _runtime_definition(item, kind):
            flush()
            expanded.append(item)
        else:
            declarative.append(item)
    flush()
    return expanded


class Recipe:
    """The Workflow Orchestrator.

    Reads data ingestion and processing recipes from YAML/JSON files
    and executes them.

    Usage:
        # Load the Recipe
        recipe = Recipe.from_file("socal_project.yaml")

        # Run it.
        recipe.run()
    """

    def __init__(self, config, base_dir=None, verbose=None):
        self.config = config
        self.base_dir = base_dir or Path.cwd()
        self.recipe_dir = self.base_dir
        self.name = "Unnamed_Recipe"
        self.verbose = verbose  # Depreciated
        if isinstance(self.config, dict):
            self.name = self.config.get("project", {}).get("name", "Unnamed_Recipe")
        else:
            raise TypeError(
                "Recipe expects a config dictionary; use Recipe.from_file() for paths."
            )

    @classmethod
    def from_file(cls, config_source):
        """Factory method to load the Recipe.
        Accepts a filename (str) or a dictionary directly.
        """

        if isinstance(config_source, dict):
            return cls(config_source)

        config_path = Path(config_source)

        if not config_path.exists():
            raise FileNotFoundError(f"Recipe not found: {config_source}")

        base_dir = config_path.resolve().parent
        ext = config_path.suffix.lower()

        with open(config_source, "r") as f:
            if ext in [".yaml", ".yml"]:
                import yaml

                config = yaml.safe_load(f)
            else:
                config = json.load(f)

        return cls(config, base_dir=base_dir)

    @classmethod
    def from_dict(cls, config):
        """Construct a recipe from Python configuration, including live objects."""
        if not isinstance(config, dict):
            raise TypeError("Recipe.from_dict expects a dictionary")
        return cls(config)

    def to_json(self, indent=2) -> str:
        """Serialize the recipe configuration to a JSON string."""

        try:
            return json.dumps(self.config, indent=indent)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "This recipe contains Python runtime components and cannot be "
                "serialized to JSON. Register the components and use their names "
                "for a declarative recipe."
            ) from exc

    def to_cli(self, executable="fetchez build") -> str:
        """Translate the recipe configuration into a runnable CLI command string."""

        if any(
            _runtime_definition(h, "hook") for h in self.config.get("global_hooks", [])
        ) or any(
            _runtime_definition(m, "module") for m in self.config.get("modules", [])
        ):
            raise TypeError(
                "Recipes containing Python runtime components cannot be converted to CLI commands."
            )
        cmd_parts = [executable]

        # Base Pipeline Arguments
        if "region" in self.config:
            cmd_parts.append(f"-R {self.config['region']}")
        if "region_srs" in self.config:
            cmd_parts.append(f"--region-srs {self.config['region_srs']}")
        if "execution" in self.config and "threads" in self.config["execution"]:
            cmd_parts.append(f"--threads {self.config['execution']['threads']}")

        # Global Hooks
        for hook in self.config.get("global_hooks", []):
            hook_name = hook.get("name") or hook.get("preset")
            args = hook.get("args", {})
            if args:
                arg_str = ",".join(
                    f"{k}={'/'.join(map(str, v)) if isinstance(v, list) else v}"
                    for k, v in args.items()
                )
                cmd_parts.append(f"--global-hook {hook_name}:{arg_str}")
            else:
                cmd_parts.append(f"--global-hook {hook_name}")

        # Modules & Bundles
        for mod in self.config.get("modules", []):
            if isinstance(mod, str):
                cmd_parts.append(mod)
                continue

            mod_name = mod.get("module") or mod.get("bundle") or mod.get("recipe")
            mod_args = mod.get("args", {})

            # Start the module segment
            mod_cmd = [mod_name]

            # Append Module Arguments (e.g., --weight 3.0)
            for k, v in mod_args.items():
                mod_cmd.append(f"--{k.replace('_', '-')} {v}")

            cmd_parts.append(" ".join(mod_cmd))

            # Append specific Module Hooks
            for hook in mod.get("hooks", []):
                hook_name = hook.get("name") or hook.get("preset")
                args = hook.get("args", {})
                if args:
                    arg_str = ",".join(
                        f"{k}={'/'.join(map(str, v)) if isinstance(v, list) else v}"
                        for k, v in args.items()
                    )
                    cmd_parts.append(f"  --hook {hook_name}:{arg_str}")
                else:
                    cmd_parts.append(f"  --hook {hook_name}")

        return " \\\n  ".join(cmd_parts)

    def to_markdown(self, config, batch_name=None):
        """Generates a Markdown receipt detailing the pipeline execution plan."""

        import datetime

        name = config.get("project", {}).get("name", "Unnamed_Recipe")
        desc = config.get("project", {}).get("description", "No description provided.")
        region = config.get("region", "Global")
        region_srs = config.get("region_srs", "EPSG:4326")

        receipt_prefix = (
            batch_name if batch_name else self.name.lower().replace(" ", "_")
        )
        receipt_filename = f"{receipt_prefix}_receipt.md"
        receipt_path = Path(self.base_dir / receipt_filename)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        region_str = (
            f"`{region}` (Native CRS: {region_srs})"
            if region and str(region) != "None"
            else "`Global / Not Specified`"
        )

        with open(receipt_path, "w", encoding="utf-8") as f:
            f.write(f"# Pipeline Execution Receipt: {name}\n")
            f.write(f"**Generated by Fetchez v{fetchez_version}**\n")
            f.write(f"*Execution Time: {timestamp}*\n\n")

            f.write("## 📝 Project Details\n")
            f.write(f"**Description:** {desc}\n\n")
            f.write(f"**Target Region:** {region_str}\n\n")
            f.write("---\n\n")

            # --- GLOBAL HOOKS ---
            f.write("## 🌐 Global Hooks\n")
            global_hooks = config.get("global_hooks", [])
            if not global_hooks:
                f.write("*None*\n\n")
            else:
                for i, hook in enumerate(global_hooks, 1):
                    h_name = _component_label(
                        hook.get("name", "Unknown") if isinstance(hook, dict) else hook
                    )
                    f.write(f"{i}. **`{h_name}`**\n")
                    for k, v in (
                        hook.get("args", {}) if isinstance(hook, dict) else {}
                    ).items():
                        f.write(f"    - `{k}`: `{v}`\n")
                f.write("\n")

            f.write("---\n\n")

            # --- MODULES & LOCAL HOOKS ---
            f.write("## 📦 Data Modules Executed\n")
            modules = config.get("modules", [])
            if not modules:
                f.write("*None*\n\n")
            else:
                for mod in modules:
                    m_name = _component_label(
                        mod.get("module", "Unknown") if isinstance(mod, dict) else mod
                    )
                    f.write(f"### 🔹 Module: `{m_name}`\n")

                    # Print fully resolved arguments
                    f.write("**Resolved Arguments:**\n")
                    args = mod.get("args", {}) if isinstance(mod, dict) else {}
                    if not args:
                        f.write("- *Defaults only*\n")
                    else:
                        for k, v in args.items():
                            f.write(f"- `{k}`: `{v}`\n")

                    # Print module-specific hooks
                    mod_hooks = mod.get("hooks", []) if isinstance(mod, dict) else []
                    if mod_hooks:
                        f.write("\n**Module Hooks:**\n")
                        for i, hook in enumerate(mod_hooks, 1):
                            h_name = _component_label(
                                hook.get("name", "Unknown")
                                if isinstance(hook, dict)
                                else hook
                            )
                            f.write(f"{i}. `{h_name}`\n")
                            for k, v in (
                                hook.get("args", {}) if isinstance(hook, dict) else {}
                            ).items():
                                f.write(f"    - `{k}`: `{v}`\n")
                    f.write("\n")

        logger.debug(f"Saved execution receipt to {receipt_filename}")

    def _check_integrity(self):
        """Ensures the fetchez version meets the recipe's minimum requirements."""

        conf = self.config.get("config", {})
        min_fz = conf.get("min_fetchez_version")

        if min_fz:
            current = _parse_version(fetchez_version)
            required = _parse_version(min_fz)
            if current < required:
                logger.error(
                    f"Recipe requires fetchez v{min_fz}, but found v{fetchez_version}"
                )
                raise RuntimeError("Fetchez version incompatibility.")

    def _resolve_path(
        self, path: str, base: Optional[str] = None
    ) -> Optional[str | Any]:
        """Resolves output paths relative to the recipe file."""

        if not isinstance(path, str):
            return path
        if path.startswith(("http", "s3://", "gs://", "ftp://")):
            return path
        if Path(path).is_absolute():
            return path
        return str(Path(Path(base or self.base_dir) / path).resolve())

    def _init_hooks(self, hook_defs, mod=None):
        """Initialize class/name hooks; pass configured instances through unchanged."""
        active_hooks = []
        input_keys = {
            "file",
            "mask_fn",
            "dem",
            "barrier",
            "aux_path",
            "path",
            "outdir",
            "cache_dir",
        }
        output_keys = {"output", "output_grid"}
        for definition in hook_defs:
            if isinstance(definition, dict):
                ref = definition.get("name")
                args = definition.get("args", {})
            else:
                ref, args = definition, {}
            resolved = resolve_component(ref, HookRegistry, FetchHook)
            if not inspect.isclass(resolved):
                if args:
                    raise ValueError(
                        f"Hook instance '{_component_label(resolved)}' is already configured; "
                        "supply a class with args instead of mutating an instance."
                    )
                active_hooks.append(resolved)
                continue
            kwargs = {
                key: self._resolve_path(value, base=self.recipe_dir)
                if key in input_keys
                else self._resolve_path(value)
                if key in output_keys
                else value
                for key, value in args.items()
            }
            active_hooks.append(resolved(**_constructor_kwargs(resolved, kwargs)))
        return active_hooks

    def _init_modules(
        self, module_defs, target_region=None, global_region_srs="EPSG:4326"
    ):
        """Create modules per batch, preserving supplied instances and their state."""
        modules_to_run = []
        for definition in module_defs:
            if isinstance(definition, dict):
                ref = definition.get("module")
                args = dict(definition.get("args", {}))
                hook_defs = definition.get("hooks", [])
                mod_region_srs = definition.get("region_srs", global_region_srs)
            else:
                ref, args, hook_defs = definition, {}, []
                mod_region_srs = global_region_srs

            resolved = resolve_component(ref, ModuleRegistry, FetchModule)
            if not inspect.isclass(resolved):
                if args or hook_defs:
                    raise ValueError(
                        f"Module instance '{_component_label(resolved)}' is already configured; "
                        "use a module class with args/hooks for batch-specific configuration."
                    )
                modules_to_run.append(resolved)
                continue

            for path_key in ("path", "outdir", "cache_dir"):
                if path_key in args:
                    args[path_key] = self._resolve_path(
                        args[path_key], base=self.recipe_dir
                    )
            mod_hooks = self._init_hooks(hook_defs)
            region = target_region
            if region is not None and region.valid_p():
                # Do not mutate the caller-owned region object in place.
                region = Region.from_list(region.to_list())
                region.srs = mod_region_srs
            kwargs = dict(args)
            kwargs.update(src_region=region, hook=mod_hooks)
            modules_to_run.append(resolved(**_constructor_kwargs(resolved, kwargs)))
        return modules_to_run

    def _init_modifiers(self, modifier_defs):
        """Looks for modifiers in the config and applies their rules."""

        ModifierRegistry.load_all()
        active_modifiers = []

        for modifier in modifier_defs:
            name = modifier.get("name")
            raw_kwargs = modifier.get("args", {})

            kwargs = {}

            input_keys = [
                "file",
                "mask_fn",
                "dem",
                "barrier",
                "aux_path",
                "path",
                "outdir",
                "cache_dir",
            ]
            output_keys = ["output", "output_grid"]

            for k, v in raw_kwargs.items():
                if k in input_keys:
                    kwargs[k] = self._resolve_path(v, base=self.recipe_dir)
                elif k in output_keys:
                    kwargs[k] = self._resolve_path(v)
                else:
                    kwargs[k] = v

            ModifierCls = ModifierRegistry.get_class(name)
            if ModifierCls:
                sig = inspect.signature(ModifierCls.__init__)

                valid_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k in sig.parameters or "kwargs" in str(sig.parameters)
                }

                active_modifiers.append(ModifierCls(**valid_kwargs))
            else:
                logger.warning(f"Modifier '{name}' missing.")

        return active_modifiers

    def _init_schemas(self, schema_defs):
        """Looks for modifiers in the config and applies their rules."""

        SchemaRegistry.load_all()
        active_schemas = []

        for schema in schema_defs:
            if isinstance(schema, dict):
                name = schema.get("name")
                SchemaCls = SchemaRegistry.get_class(name)
                if SchemaCls:
                    active_schemas.append(SchemaCls())
                else:
                    logger.warning(f"Schema '{name}' missing.")
            else:
                logger.debug("Invalid schema formatting: {schema}")

        return active_schemas

    def _inject_batch_context(self, config_block: Any, **kwargs) -> Any:
        """Recursively formats strings in the config to inject runtime context variables."""

        if isinstance(config_block, dict):
            return {
                k: self._inject_batch_context(v, **kwargs)
                for k, v in config_block.items()
            }
        elif isinstance(config_block, list):
            return [self._inject_batch_context(v, **kwargs) for v in config_block]
        elif isinstance(config_block, str) or isinstance(config_block, Path):
            res = str(config_block)
            for key, val in kwargs.items():
                if val is not None:
                    res = res.replace(f"%{key}%", str(val))
            return res

        return config_block

    def _get_module_signature(self, mod_dict):
        """Creates a unique signature for a module to handle deduplication.
        Ensures that 'tnm' (dataset 1) does not collide with 'tnm' (dataset 3).
        """

        if isinstance(mod_dict, str):
            return mod_dict

        m_name = mod_dict.get("module")
        if not m_name:
            return str(mod_dict)

        args = mod_dict.get("args", {})

        # Ids that make a dataset truly unique within a module
        ids = []
        for key in [
            "datatype",
            "datasets",
            "formats",
            "layer",
            "product",
            "survey_id",
            "url",
            "path",
        ]:
            if key in args:
                ids.append(f"{key}={args[key]}")

        if ids:
            return f"{m_name}::" + "::".join(sorted(ids))
        return m_name

    def _expand_modules(self, raw_modules, parent_weight=1.0):
        """Delegates module/bundle expansion directly to BundleRegistry."""

        return _expand_declarative_segments(
            raw_modules,
            BundleRegistry.expand_modules,
            "module",
            parent_weight=parent_weight,
        )

    def _expand_hooks(self, hook_defs, parent_hooks=None):
        """Delegates hook/preset expansion directly to PresetRegistry."""

        return _expand_declarative_segments(
            hook_defs, PresetRegistry.expand_hooks, "hook", parent_hooks=parent_hooks
        )

    # TODO: break up this function.
    # Yield the config for each iteration, etc.
    def run(
        self,
        outdir: Optional[str] = None,
        shared_cache: Optional[str] = None,
        overwrite: bool = False,
        refresh: bool = False,
        ignore_failures: bool = False,
    ):
        """Execute the recipe, supporting vector-based batching, caching, and resumption."""

        ModuleRegistry.load_all()
        BundleRegistry.load_all()
        ModifierRegistry.load_all()
        SchemaRegistry.load_all()

        if not self.config:
            return

        self._check_integrity()
        # Check for 'domain' to see if we have the proper extension to run the recipe.
        # Maybe add something like this to _check_integrity
        # domain = self.config.get("domain")

        # Execution parameters
        run_opts = self.config.get("execution", {})
        threads = run_opts.get("threads", 1)
        raw_region = self.config.get("region")
        global_region_srs = self.config.get("region_srs", "EPSG:4326")
        recipe_name = self.config.get("project", {}).get("name", "Unnamed")

        original_cwd = Path.cwd()
        if outdir is None:
            base_outdir = original_cwd.resolve()
        else:
            base_outdir = Path(outdir).resolve()

        # State Tracking
        state_file = Path(base_outdir / "fetchez_batch_state.json")
        completed_tiles = []
        if state_file.exists() and not overwrite:
            try:
                with open(state_file, "r") as f:
                    completed_tiles = json.load(f)
            except Exception:
                pass

        # Shared Cache
        abs_cache = None
        if shared_cache:
            abs_cache = Path(shared_cache).resolve()
            abs_cache.mkdir(parents=True, exist_ok=True)
            logger.info(f"Shared cache enabled: {abs_cache}")

        # Batch Loop
        for i, (target_region, feat_name) in enumerate(
            yield_parsed_regions(raw_region)
        ):
            # Batch Name
            if feat_name:
                batch_name = str(feat_name)
            elif target_region and i > 0:
                batch_name = f"batch_{i:03d}"
            else:
                batch_name = None

            # Check State
            if batch_name and batch_name in completed_tiles and not overwrite:
                logger.info(
                    f"Skipping completed tile: {batch_name} (use --overwrite to force)"
                )
                continue

            iteration_config = _safe_config_copy(self.config)

            # Setup the Sub-Folder
            tile_dir = base_outdir  # original_cwd
            if batch_name:
                logger.info(
                    colorize(f"\n--- Running Batch Iteration: {batch_name} ---", CYAN)
                )
                orig_name = iteration_config.get("project", {}).get("name", "Unnamed")
                iteration_config.setdefault("project", {})["name"] = (
                    f"{orig_name}_{batch_name}"
                )

                tile_dir = Path(tile_dir / batch_name)

            tile_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(tile_dir)

            try:
                # Local Region
                if target_region:
                    iteration_config["region"] = target_region.to_list()

                # Initialize & Run Pipeline
                self.base_dir = tile_dir

                # Expand Hooks and Modules
                iteration_config["global_hooks"] = self._expand_hooks(
                    iteration_config.get("global_hooks", [])
                )
                iteration_config["modules"] = self._expand_modules(
                    iteration_config.get("modules", [])
                )

                for mod in iteration_config["modules"]:
                    if isinstance(mod, dict):
                        mod["hooks"] = self._expand_hooks(mod.get("hooks", []))

                # Apply any Modifiers and validate with any Schemas
                iteration_config_modified = _safe_config_copy(iteration_config)
                modifiers = self._init_modifiers(iteration_config.pop("modifiers", []))
                for modifier in modifiers:
                    iteration_config_modified = modifier.apply(
                        iteration_config_modified
                    )
                iteration_config_modified.pop("modifiers", None)
                iteration_config = _safe_config_copy(iteration_config_modified)

                # Inject outdir for shared caching
                for mod in iteration_config.get("modules", []):
                    if not isinstance(mod, dict):
                        continue  # A supplied module instance/class owns its own configuration.
                    if isinstance(mod.get("module"), FetchModule):
                        continue
                    if refresh:
                        mod.setdefault("args", {})["use_cache"] = False
                    if abs_cache and mod.get("module") not in [
                        "file",
                        "local_fs",
                        "stdin",
                    ]:
                        mod.setdefault("args", {})["outdir"] = abs_cache
                        # for hook in mod.get("hooks", []):
                        #     if abs_cache or tile_dir:
                        #         for arg in hook.get("args", {}):
                        #             if arg in ["cache_dir", "outdir"]:
                        #                 hook.setdefault("args", {})[arg] = abs_cache or tile_dir

                if batch_name or target_region:
                    # Inject the %place-holder% context into outputs
                    iteration_config = self._inject_batch_context(
                        iteration_config,
                        name=self.config.get("project", {}).get("name", "fetchez"),
                        batch_name=batch_name
                        or (target_region.format("fn") if target_region else ""),
                        shared_cache=abs_cache or tile_dir,
                        cache_dir=abs_cache or tile_dir,
                        outdir=base_outdir,
                        tile_dir=tile_dir,
                        region_srs=global_region_srs,
                    )

                schemas = self._init_schemas(iteration_config.get("schemas", []))
                errors = []
                for schema in schemas:
                    logger.info(f"Validating recipe with {schema.name} schema")
                    iteration_valid, iteration_errors = schema.run(iteration_config)
                    if not iteration_valid:
                        errors.extend(iteration_errors)

                if len(errors) > 0:
                    logger.warning(
                        f"The recipe is invalid based on defined schemas: {errors}"
                    )

                iteration_region = iteration_config.get("region", [])

                # Initialize Hooks and Modules ( to python classes )
                try:
                    global_hooks = self._init_hooks(iteration_config["global_hooks"])
                except Exception as e:
                    logger.error(f"Could not initialize recipe global hooks: {e}")
                    if not ignore_failures:
                        raise
                    continue

                try:
                    modules_to_run = self._init_modules(
                        iteration_config["modules"],
                        target_region=Region.from_list(iteration_region or []),
                        global_region_srs=global_region_srs,
                    )
                except Exception as e:
                    logger.error(f"Could not initialize recipe modules: {e}")
                    if not ignore_failures:
                        raise
                    continue

                if not modules_to_run:
                    continue

                # # Dump the localized recipe for debugging and reproducibility
                # batch_config_fn = f"{batch_name or recipe_name}_recipe.yaml"

                # batch_dir = Path(batch_config_fn).resolve().parent
                # if batch_dir:
                #     batch_dir.mkdir(parents=True, exist_ok=True)

                # with open(batch_config_fn, "w") as f:
                #     yaml.dump(
                #         iteration_config,
                #         f,
                #         sort_keys=False,
                #         default_flow_style=False,
                #     )
                # logger.debug(f"Saved localized recipe to {batch_config_fn}")

                self.to_markdown(iteration_config, batch_name)

                for mod in modules_to_run:
                    try:
                        mod.run()
                    except Exception as e:
                        if ignore_failures:
                            logger.error(f"[{mod.name}] Module execution failed: {e}")
                            logger.warning(
                                f"[{mod.name}] 'ignore-failures' is SET. "
                                "Pipeline will continue, but your final output may be incomplete!"
                            )
                        else:
                            # Default behavior: Fail and abort
                            logger.critical(
                                f"[{mod.name}] Fatal error encountered. Aborting pipeline to prevent incomplete data generation. "
                                "Set 'ignore_failures' if you wish to bypass this."
                            )
                            raise

                try:
                    tracemalloc.start()
                    run_fetchez(
                        modules_to_run,
                        threads=threads,
                        global_hooks=global_hooks,
                        ignore_failures=ignore_failures,
                    )
                    current, peak = tracemalloc.get_traced_memory()
                    logger.info(
                        f"Pipeline Memory Usage - Current: {current / 10**6:.2f} MB | Peak: {peak / 10**6:.2f} MB"
                    )

                    tracemalloc.stop()

                except Exception as e:
                    if ignore_failures:
                        logger.error(f"fetchez execution failed: {e}")
                        logger.warning(
                            f"[{mod.name}] 'ignore-failures' is SET. "
                            "Pipeline will continue, but your final output may be incomplete!"
                        )
                    logger.critical(
                        "Fatal error encountered. Aborting pipeline to prevent incomplete data generation. "
                        "Set 'ignore_failures' if you wish to bypass this."
                    )
                    raise

                # Update State
                if batch_name:
                    completed_tiles.append(batch_name)
                    with open(state_file, "w") as f:
                        json.dump(completed_tiles, f, indent=2)

                yield (
                    iteration_config,
                    target_region,
                    batch_name
                    or recipe_name
                    or (target_region.format("fn") if target_region else ""),
                    abs_cache or tile_dir,
                    base_outdir,
                    tile_dir,
                )

            except Exception as e:
                logger.exception(f"Batch '{batch_name or 'run'}' failed: {e}")
                logger.warning(
                    "Batch processing halted. Re-run command to resume from this tile."
                )
                raise

            finally:
                self.base_dir = original_cwd
                os.chdir(original_cwd)

        logger.debug(f"Batch execution complete for {self.name}")
