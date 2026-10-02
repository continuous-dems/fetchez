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
    colorize,
    CYAN,
    GREEN,
    BOLD,
    FetchezMainGroup,
    FetchezMainCommand,
)


def add_options(options):
    def decorator(f):
        for opt in reversed(options or []):
            f = click.option(opt[0], default=opt[2], help=opt[1])(f)
        return f

    return decorator


def _module_cli_options(mod_meta):
    """Return dynamically generated Click options for a module."""
    options = []

    for key, val in mod_meta.get("cli_args", {}).items():
        if key in {
            "self",
            "kwargs",
            "src_region",
            "callback",
            "name",
            "params",
            "hook",
            "weight",
        }:
            continue

        options.append([f"--{key.replace('_', '-')}", val["desc"], val["default"]])

    return options


def _parse_bundle_selectors(values):
    def _parse_selector_value(value):
        try:
            return yaml.safe_load(value)
        except Exception:
            return value

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
    mod_args = _module_cli_options(mod_meta)

    @click.command(name=name, help=help_text, hidden=True, cls=FetchezMainCommand)
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

    @click.command(name=name, help=help_text, hidden=True, cls=FetchezMainCommand)
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
            "hooks": parsed_hooks,
        }

        if selectors:
            result["select"] = selectors

        return result

    return bundle_cmd


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


# class PipelineExecutor(click.Group):
class PipelineExecutor(FetchezMainGroup):
    def list_commands(self, ctx):
        ModuleRegistry.load_all()
        BundleRegistry.load_all()

        names = set(ModuleRegistry.get_registry())
        names.update(BundleRegistry.get_registry())
        return sorted(names)

    def get_command(self, ctx, name):
        ModuleRegistry.load_all()
        mod_meta = ModuleRegistry.get_info(name)
        if mod_meta:
            return make_module_command(name, mod_meta)

        BundleRegistry.load_all()
        bundle_yml = BundleRegistry.get_yaml(name)
        if bundle_yml:
            return make_bundle_command(name, bundle_yml)
        return None

    def format_commands(self, ctx, formatter):
        """Override the default Click help to group modules by category."""

        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        grouped_commands = {}
        for name, cmd in commands:
            mod_meta = ModuleRegistry.get_info(name)

            if mod_meta:
                category = mod_meta.get("category", "Other Modules")
            else:
                category = f"{colorize(colorize('Curated Data Bundles', GREEN), BOLD)}"

            if category not in grouped_commands:
                grouped_commands[category] = []

            grouped_commands[category].append((name, cmd))

        # Print the bundles first, then alphabetize the remaining categories
        bundle_key = f"{colorize(colorize('Curated Data Bundles', GREEN), BOLD)}"
        if bundle_key in grouped_commands:
            with formatter.section(bundle_key):
                formatter.write_dl(
                    [
                        (
                            f"{colorize(colorize(name, CYAN), BOLD):<30}",
                            cmd.get_short_help_str(limit=80),
                        )
                        for name, cmd in grouped_commands.pop(bundle_key)
                    ]
                )

        # Print the rest of the categories
        for category, cmds in sorted(grouped_commands.items()):
            formatted_category = (
                f"{colorize(colorize(category, GREEN), BOLD)}"
                if category != "Other Modules"
                else category
            )

            with formatter.section(formatted_category):
                formatter.write_dl(
                    [
                        (
                            f"{colorize(colorize(name, CYAN), BOLD):<30}",
                            cmd.get_short_help_str(limit=80),
                        )
                        for name, cmd in cmds
                    ]
                )


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
    """Build and optionally execute a pipeline from modules and bundles.

    \b
    The `build` command composes an ad-hoc Fetchez recipe from registered
    Modules and Bundles, optionally attaching processing Hooks and Presets.

    \b
    Use `--export` to save the constructed pipeline as a reusable YAML recipe
    instead of executing it immediately.

    \b
    How CLI Pipelines Work:
      The `build` command allows you to chain multiple Data Modules together
      and apply Processing Hooks to them.

    \b
      * Module Arguments follow the module name (e.g., `copernicus --datatype 3`).
      * Module Hooks (--hook) apply only to the module they follow.
      * Global Hooks (--global-hook) apply to all data flowing through the pipeline.

    \b
    Syntax:
      fetchez build -R <W/E/S/N> [--global-hook <name>] <module_1> [--hook <name>] <module_2> ...

    \b
    Compose interactively:
      fetchez build -R ... glob-tnm --select products=1m/1_9as --export dem.yaml

    \b
    Reproduce later:
      fetchez run dem.yaml

    \b
    * Run `fetchez modules` to learn more about supported modules and extensions..
    * Run `fetchez hooks` to learn more about supported hooks and extensions.
    """

    # \b
    # Examples:
    #   # Fetch lidar data from NOAAs Digtial Coast and filter out files containing the word "noise"
    #   $ fetchez build -R loc:seattle digital_coast --hook filename_filter:exclude=noise,stage=manifest

    #   # Fetch multibeam and topography, and run an audit on everything
    #   $ fetchez build -R -120/-119/33/34 --global-hook audit mbdb tnm

    #   # Export a complex CLI pipeline to a YAML recipe without running it
    #   $ fetchez build -R loc:hawaii --export hawaii_recipe.yaml copernicus --weight 1.5 mbdb

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

    modules = [cmd for cmd in commands if cmd.pop("type", None) == "module"]

    parsed_global_hooks = []
    for h in global_hook:
        parsed_h = parse_hook_string(h)
        if parsed_h.get("name") in PresetRegistry.get_registry().keys():
            parsed_h["preset"] = parsed_h.pop("name")
        elif parsed_h.get("name") not in HookRegistry.get_registry().keys():
            click.secho(
                f"Warning: Hook or Preset '{h}' not found in registry! Skipping.",
                fg="yellow",
            )
            continue
        parsed_global_hooks.append(parsed_h)

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
