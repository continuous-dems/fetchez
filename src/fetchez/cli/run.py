#!/usr/bin/env python

"""
fetchez.cli.pipeline
~~~~~~~~~~~~~~~~

Genreate and run a fetchez pipeline.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path

import click

from fetchez.recipe import Recipe, load_recipe_config
from fetchez.registry import (
    RecipeRegistry,
)
from fetchez.spatial import region_help_msg
from fetchez.utils import (
    FetchezMainCommand,
    parse_hook_string,
)


@click.command("run", cls=FetchezMainCommand)
@click.option(
    "-R",
    "--region",
    help=f"""\b
Bounding box (W/E/S/N)
{region_help_msg()}
""",
)
@click.option(
    "-D",
    "--outdir",
    type=click.Path(resolve_path=True),
    default=None,
    help="Base output directory for recipe outputs.",
)
@click.option(
    "--region-srs",
    default="EPSG:4326",
    help="Set the SRS of the input bounding box (default: EPSG:4326).",
)
@click.option(
    "--shared-cache",
    type=click.Path(resolve_path=True),
    help="Centralized directory to cache fetched data.",
)
@click.option(
    "--modifier", multiple=True, help="Apply a recipe modifier to mutate the pipeline."
)
@click.option(
    "--schema", multiple=True, help="Apply validation schemas (e.g., 'cudem')."
)
@click.option(
    "--refresh", is_flag=True, help="Force fresh API fetch, bypassing local cache."
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Raise an exception on the first failure, otherwise continue processing through failures.",
)
@click.argument("name")
def run_recipe(
    name,
    region,
    region_srs,
    outdir,
    shared_cache,
    modifier,
    schema,
    refresh,
    fail_fast,
):
    """Execute a Fetchez recipe.

    \b
    NAME may be either:
      * a registered recipe name, such as `socal-crm-standard`
      * a path to a local YAML recipe

    \b
    Recipes define complete, reproducible processing workflows using Fetchez
    modules, bundles, hooks, presets, modifiers, and schemas.

    Runtime options may override selected recipe settings without modifying
    the original recipe. For example, `--region` can run the same workflow
    over a different area, while `--shared-cache` and `--outdir` control
    execution storage.

    \b
    Examples:

    \b
      # Run a registered recipe
      fetchez run socal-crm-standard

    \b
      # Run it over a different region
      fetchez run -R crm_tiles.geojson socal-crm-standard

    \b
      # Run a local recipe file
      fetchez run my_pipeline.yaml

    \b
      # Share downloaded data between repeated or tiled runs
      fetchez run my_pipeline.yaml --shared-cache ./data --outdir ./output

    \b
    Use `fetchez recipes list` to discover registered recipes and
    `fetchez recipes info <name>` to inspect one before running it.
    """

    RecipeRegistry.load_all()

    click.secho(f"Executing YAML recipe: {name}...", fg="cyan", bold=True)

    base_config = None
    if Path(name).exists():
        base_config = load_recipe_config(name)

    if not base_config:
        meta = RecipeRegistry.get_yaml(name)
        if not meta:
            click.secho(f"Error: Recipe '{name}' not found.", fg="red")
        base_config = meta.get("config", {})

    if not base_config:
        raise click.ClickException(
            f"Recipe '{name}' was not found as a file or registered recipe."
        )

    if region:
        base_config["region"] = region
        click.secho(f"Overriding recipe region to: {region}", fg="yellow")

        if region_srs:
            base_config["region_srs"] = region_srs

        global_hooks = base_config.get("global_hooks", [])
        for hook in global_hooks:
            hook_args = hook.get("args", [])
            for arg in hook_args:
                if arg == "region":
                    hook_args[arg] = region
                    click.secho(
                        f"Overriding recipe hook {hook.get('name', 'unknown')} region to: {region}",
                        fg="yellow",
                    )

    try:
        parsed_modifiers = [parse_hook_string(m) for m in modifier]
        parsed_schemas = [s for s in schema]

        if parsed_modifiers:
            base_config["modifiers"] = parsed_modifiers

        if schema:
            base_config["schemas"] = parsed_schemas

        recipe = Recipe.from_dict(base_config)

        [
            r
            for r in recipe.run(
                outdir=outdir,
                shared_cache=shared_cache,
                refresh=refresh,
                ignore_failures=not fail_fast,
            )
        ]

        click.secho(f"✨ Successfully executed {name} recipe!", fg="green", bold=True)

    except Exception as e:
        click.secho(f"Failed to execute {name} recipe!: {e!s}", fg="red", bold=True)
