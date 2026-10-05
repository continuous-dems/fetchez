#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.pipeline
~~~~~~~~~~~~~~~~

Build a fetchez pipeline.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click
import yaml
from fetchez.recipe import Recipe
from fetchez.registry import (
    ModuleRegistry,
    BundleRegistry,
    PresetRegistry,
    HookRegistry,
    # SchemaRegistry,
)
from fetchez.spatial import parse_region, region_help_msg
from fetchez.utils import (
    parse_hook_string,
    parse_arg_to_list,
    FetchezMainGroup,
    FetchezMainCommand,
)


def add_options(options):
    def decorator(f):
        for opt in reversed(options or []):
            f = click.option(opt[0], default=opt[2], help=opt[1])(f)
        return f

    return decorator


def _component_cli_options(meta, exclude=None):
    exclude = set(exclude or ())
    exclude.update(
        {
            "self",
            "kwargs",
            "src_region",
            "callback",
            "name",
            "params",
        }
    )

    options = []

    for key, val in meta.get("cli_args", {}).items():
        if key in exclude:
            continue

        options.append(
            [
                f"--{key.replace('_', '-')}",
                val["desc"],
                val["default"],
            ]
        )

    return options


def _parse_bundle_selectors(values):
    def _parse_selector_value(value):
        try:
            return yaml.safe_load(value)
        except yaml.YAMLError:
            return value
        except Exception:
            raise

    selectors = {}
    for value in values or []:
        if "=" not in value:
            raise click.BadParameter(f"Invalid selector '{value}'. Expected KEY=VALUE.")

        key, raw_value = value.split("=", 1)
        key = key.strip()

        if not key:
            raise click.BadParameter(
                f"Invalid selector '{value}'. Missing selector key."
            )

        values = parse_arg_to_list(raw_value, str)
        parsed = [_parse_selector_value(value) for value in values]

        selectors[key] = parsed[0] if len(parsed) == 1 else parsed

    return selectors


def make_module_command(name, mod_meta):
    help_text = mod_meta.get("cli_help_text", f"Run the {name} module")
    mod_args = _component_cli_options(
        mod_meta,
        exclude={"hook", "weight"},
    )

    @click.command(name=name, help=help_text, hidden=False, cls=FetchezMainCommand)
    @click.option("--weight", type=float, default=1.0)
    @click.option("--hook", multiple=True, help="Attach a processing hook")
    @add_options(mod_args)
    def dynamic_module_cmd(weight, hook, **kwargs):
        parsed_hooks = [parse_hook_string(h) for h in hook]
        return {
            "type": "module",
            "module": name,
            "args": {"weight": weight, **kwargs},
            "hooks": parsed_hooks,
        }

    return dynamic_module_cmd


def make_bundle_command(name, bundle_def):
    help_text = bundle_def.get("description", "")

    @click.command(name=name, help=help_text, hidden=False, cls=FetchezMainCommand)
    @click.option("--weight", type=float, default=1.0)
    @click.option(
        "--select",
        type=str,
        multiple=True,
        metavar="KEY=VALUE",
        help=(
            "Select bundle members by configuration value. "
            "Slash-delimit multiple accepted values."
        ),
    )
    @click.option("--hook", multiple=True, help="Attach a processing hook")
    def bundle_cmd(weight, select, hook):
        selectors = _parse_bundle_selectors(select)
        parsed_hooks = [parse_hook_string(h) for h in hook]
        result = {
            "type": "module",
            "bundle": name,
            "args": {
                "weight": weight,
            },
            "append_hooks": parsed_hooks,
        }

        if selectors:
            result["select"] = selectors

        return result

    return bundle_cmd


def make_hook_command(name, hook_def):
    help_text = hook_def.get(
        "cli_help_text",
        f"Apply the {name} hook",
    )
    hook_args = _component_cli_options(hook_def)

    @click.command(
        name=name,
        help=help_text,
        hidden=False,
        cls=FetchezMainCommand,
    )
    @add_options(hook_args)
    def dynamic_hook_cmd(**kwargs):
        return {
            "type": "hook",
            "name": name,
            "args": kwargs,
        }

    return dynamic_hook_cmd


def make_preset_command(name, preset_def):
    help_text = preset_def.get(
        "description",
        f"Apply the {name} preset",
    )

    @click.command(
        name=name,
        help=help_text,
        hidden=False,
        cls=FetchezMainCommand,
    )
    def dynamic_preset_cmd():
        return {
            "type": "preset",
            "preset": name,
        }

    return dynamic_preset_cmd


def make_pipeline_config(
    commands,
    *,
    name="cli_pipeline",
    region=None,
    region_srs="EPSG:4326",
    global_hooks=None,
    modifiers=None,
    schemas=None,
    threads=1,
):
    config = {
        "project": {
            "name": name,
        },
        "region": str(region) if region else None,
        "region_srs": region_srs,
        "modules": commands,
        "global_hooks": global_hooks or [],
    }

    if modifiers:
        config["modifiers"] = modifiers

    if schemas:
        config["schemas"] = schemas

    if threads:
        config["execution"] = {
            "threads": threads,
        }

    return config


def _attach_module_hook(component, hook):
    if "bundle" in component:
        component.setdefault("append_hooks", []).append(hook)
    else:
        component.setdefault("hooks", []).append(hook)


def organize_pipeline_commands(commands):
    modules = []
    global_hooks = []
    current_module = None

    for command in commands:
        command_type = command.get("type")

        if command_type == "module":
            current_module = {
                key: value for key, value in command.items() if key != "type"
            }
            modules.append(current_module)
            continue

        if command_type in {"hook", "preset"}:
            hook = {key: value for key, value in command.items() if key != "type"}

            if current_module is None:
                global_hooks.append(hook)
            else:
                _attach_module_hook(current_module, hook)

            continue

        raise ValueError(f"Unsupported pipeline command type: {command_type!r}")

    return modules, global_hooks


# class PipelineExecutor(click.Group):
class PipelineExecutor(FetchezMainGroup):
    def module_allowed(self, name, meta):
        return True

    def bundle_allowed(self, name, bundle):
        return True

    def hook_allowed(self, name, meta):
        return True

    def preset_allowed(self, name, preset):
        return True

    def list_commands(self, ctx):
        ModuleRegistry.load_all()
        BundleRegistry.load_all()
        HookRegistry.load_all()
        PresetRegistry.load_all()

        names = {
            name
            for name, meta in ModuleRegistry.get_registry().items()
            if self.module_allowed(name, meta)
        }

        names.update(
            name
            for name, bundle in BundleRegistry.get_registry().items()
            if self.bundle_allowed(name, bundle)
        )

        names.update(
            name
            for name, meta in HookRegistry.get_registry().items()
            if self.hook_allowed(name, meta)
        )

        names.update(
            name
            for name, preset in PresetRegistry.get_registry().items()
            if self.preset_allowed(name, preset)
        )

        return sorted(names)

    def get_command(self, ctx, name):
        ModuleRegistry.load_all()

        mod_meta = ModuleRegistry.get_info(name)
        if mod_meta:
            if not self.module_allowed(name, mod_meta):
                return None
            return make_module_command(name, mod_meta)

        BundleRegistry.load_all()

        bundle_def = BundleRegistry.get_yaml(name)
        if bundle_def:
            if not self.bundle_allowed(name, bundle_def):
                return None
            return make_bundle_command(name, bundle_def)

        HookRegistry.load_all()
        hook_meta = HookRegistry.get_info(name)

        if hook_meta:
            if not self.hook_allowed(name, hook_meta):
                return None
            return make_hook_command(name, hook_meta)

        PresetRegistry.load_all()
        preset_def = PresetRegistry.get_yaml(name)

        if preset_def:
            if not self.preset_allowed(name, preset_def):
                return None
            return make_preset_command(name, preset_def)

        return None

    def format_commands(self, ctx, formatter):
        # Dynamic pipeline components are intentionally omitted from build help.
        # Discover them through the registry-specific list commands instead.
        pass


@click.command(
    cls=PipelineExecutor,
    chain=True,
    # epilog="\bhttps://fetchez.readthedocs.io/en/latest/index.html"
)
@click.option(
    "-R",
    "--region",
    help=f"""\b
Bounding box (W/E/S/N)
{region_help_msg()}
""",
)
@click.option(
    "--region-srs",
    default="EPSG:4326",
    help="Set the SRS of the input bounding box (default: EPSG:4326).",
)
@click.option("--global-hook", multiple=True, help="Attach a global processing hook.")
@click.option(
    "--modifier", multiple=True, help="Apply a recipe modifier to mutate the pipeline."
)
@click.option(
    "--schema", multiple=True, help="Apply validation schemas (e.g., 'cudem')."
)
@click.option(
    "--threads", default=1, help="Number of parallel download threads (default: 1)."
)
@click.option(
    "--export", type=click.Path(), help="Export to YAML instead of executing."
)
@click.option(
    "--shared-cache",
    type=click.Path(resolve_path=True),
    help="Centralized directory to cache fetched data.",
)
@click.option(
    "--refresh", is_flag=True, help="Force fresh API fetch, bypassing local cache."
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Raise an exception on the first failure, otherwise continue processing through failures.",
)
@click.pass_context
# """Initializes the context before the chained subcommands run."""
def pipeline_group(
    ctx,
    region,
    region_srs,
    export,
    global_hook,
    modifier,
    schema,
    threads,
    shared_cache,
    refresh,
    fail_fast,
):
    """
Build and optionally execute an ad-hoc Fetchez pipeline.

The `build` command composes registered Modules, Bundles, Hooks, and Presets
into a Fetchez recipe. Components are chained from left to right and may be
executed immediately or exported as reusable YAML.

Pipeline Composition:

  Source components are Modules or Bundles.

  \b
  Processing components are Hooks or Presets. Their scope is determined by
  their position in the command chain:

    \b
    * Hooks and Presets before the first source are global.
    * Hooks and Presets after a Module or Bundle apply to that source.
    * Processing components continue to apply to the most recent source
      until another Module or Bundle is encountered.

  Module and Hook arguments follow the component they configure.

Examples:

  Apply a global hook before fetching a source:

    fetchez build audit tnm

      \b
      audit -> global hook
      tnm   -> module

  Attach processing to a single source:

    fetchez build tnm raster_warp --res 1s

      \b
      tnm         -> module
      raster_warp -> hook attached to tnm

  Compose multiple independently processed sources:

    \b
    fetchez build \\
        audit \\
        tnm raster_warp --res 1s \\
        copernicus checksum

      \b
      audit       -> global hook
      tnm         -> first module
      raster_warp -> hook attached to tnm
      copernicus  -> second module
      checksum    -> hook attached to copernicus

  Select members of a registered bundle:

    \b
    fetchez build \\
        -R <W/E/S/N> \\
        glob-tnm --select products=1m/1_9as

Hooks may also be supplied using `--hook` and `--global-hook` for concise or
backward-compatible command construction.

Use `--export` to write the generated recipe to YAML instead of executing it:

    fetchez build -R <W/E/S/N> --export pipeline.yaml tnm audit

The exported recipe can later be reproduced with:

    fetchez run pipeline.yaml

Component Discovery:

    \b
    fetchez modules list           List available data modules
    fetchez modules bundles list   List curated data bundles
    fetchez hooks list             List processing hooks
    fetchez hooks presets list     List hook presets

Use any registered component directly in the build chain.
Run `fetchez build <component> --help` to inspect its component-specific options.
    """

    ctx.ensure_object(dict)
    src_region = parse_region(region) if region else None
    ctx.obj["region"] = src_region
    ctx.obj["export"] = export
    # ctx.obj["global_hook"] = parsed_global_hooks


@pipeline_group.result_callback()
def process_pipeline(
    commands,
    region,
    region_srs,
    export,
    global_hook,
    modifier,
    schema,
    threads,
    shared_cache,
    refresh,
    fail_fast,
):
    """Executes after all chained commands have returned their dictionaries."""

    HookRegistry.load_all()
    PresetRegistry.load_all()

    modules, command_global_hooks = organize_pipeline_commands(commands)

    parsed_global_hooks = []
    for h in global_hook:
        parsed_h = parse_hook_string(h)
        if parsed_h.get("name") in PresetRegistry.get_registry().keys():
            parsed_h["preset"] = parsed_h.pop("name")
        elif parsed_h.get("name") not in HookRegistry.get_registry().keys():
            if not fail_fast:
                click.secho(
                    f"Warning: Hook or Preset '{h}' not found in registry!",
                    fg="yellow",
                )
                continue
            else:
                raise ValueError(f"Hook or Preset '{h}' not found in registry!")

        parsed_global_hooks.append(parsed_h)

    parsed_global_hooks.extend(command_global_hooks)

    # parsed_global_hooks = [parse_hook_string(h) for h in global_hook]
    parsed_modifiers = [parse_hook_string(m) for m in modifier]
    parsed_schemas = [s for s in schema]

    # Build the recipe configuration dictionary
    config = make_pipeline_config(
        modules,
        region=region,
        region_srs=region_srs,
        global_hooks=parsed_global_hooks,
        modifiers=parsed_modifiers,
        schemas=parsed_schemas,
        threads=threads,
    )

    if export:
        with open(export, "w", encoding="utf-8") as f:
            yaml.dump(config, f, sort_keys=False)
        click.secho(f"Pipeline recipe exported to {export}", fg="green", bold=True)
    else:
        click.secho("Executing dynamic pipeline...", fg="cyan", bold=True, err=True)
        [
            r
            for r in Recipe.from_dict(config).run(
                shared_cache=shared_cache,
                refresh=refresh,
                ignore_failures=not fail_fast,
            )
        ]
