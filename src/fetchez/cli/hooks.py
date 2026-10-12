#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.hooks
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing hooks.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click

from fetchez.registry import HookRegistry
from fetchez.cli.utils import (
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
    filter_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.api import search_hooks
from .presets import presets_group

HOOKS_COMMANDS = ["info", "list", "providers", "presets"]


@click.group(
    cls=FetchezMainGroup,
    name="hooks",
    fetchez_commands=HOOKS_COMMANDS,
)
def hooks_group():
    """Discover, search, and learn about data processors.

    Hooks are modular processing steps (filters, transforms, algorithms)
    that manipulate data streams or files in a pipeline.

    \b
    How to use Hooks:
      1. In YAML Recipes: Defined under `hooks` (per-module) or `global_hooks`.
      2. In CLI Commands: Appended directly to data sources using the --hook switch
         or globally with --globl-hook.

    \b
    * Hooks take a fetchez entry dictionary as input and they return a fetchez dictionary
      as output.
    * Along the way, they may manipulate that entry dictionary in different ways, such as
      by modifying entry values, creating artifacts, adding data streams, adding metadata,
      etc.
    * Use `fetchez hooks info <hook-name>` to get more information about what a hook does.

    \b
    Hooks run in different stages of the pipeline:
      1. Manifest    : Runs on the initial file manifest before any fetching begins.
      2. File        : Runs of a fetched or local file.
      3. Stream      : Runs on an in-memory data stream of the fetched file.
      4. Collection  : Runs on the final collection of data that has been through the
                       previous stages.

    \b
    This command group lets you explore the available Data 'Hooks' and the multi-hook
    'Presets' that can be injected into Fetchez pipelines..
    """

    pass


@hooks_group.command("search", cls=FetchezMainCommand)
@click.argument("term")
@click.option(
    "--provider",
    "-p",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
def hook_search(term, provider):
    """Search all available processing hooks by keyword."""

    registry = search_hooks(term)
    registry = filter_registry(
        registry,
        {
            "provider": provider,
        },
    )
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Hooks", "Provider")
    click.echo("\nRun 'fetchez hooks info <name>' for arguments and recipe examples.\n")


@hooks_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s")
@click.option(
    "--group-by",
    type=click.Choice(["provider", "category", "stage", "effects"]),
    default="provider",
)
@click.option("--effect", multiple=True)
@click.option("--accepts", multiple=True)
@click.option("--produces", multiple=True)
@click.option("--stage", multiple=True)
@click.option(
    "--provider",
    "-p",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
def hook_list(search, group_by, effect, accepts, produces, stage, provider):
    registry = search_hooks(search)

    registry = filter_registry(
        registry,
        {
            "provider": provider,
            "effects": effect,
            "accepts": accepts,
            "produces": produces,
            "stage": stage,
        },
    )

    group_key = "provider" if group_by == "provider" else group_by

    grouped = group_registry_by_key(registry, group_key)
    print_grouped_registry(grouped, "Hooks", group_by.title())


@hooks_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def hook_info(name):
    """Show arguments and YAML recipe examples for a specific hook."""

    HookRegistry.load_all()
    hook_cls = HookRegistry.get_class(name)
    meta = HookRegistry.get_info(name)

    if not hook_cls:
        click.secho(f"Error: Hook '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n🪝 HOOK: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Stage       : {meta.get('stage', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}\n")

    # print_class_arguments(hook_cls)
    args_dict = get_class_arguments(hook_cls)

    click.secho("  Arguments:", fg="yellow", bold=True)
    for key, val in args_dict.items():
        click.echo(
            f"    - {click.style(key, bold=True)} {val['default']}{val['inherit']}{val['desc']}"
        )

    # Generate the YAML Snippet
    click.secho("\n  YAML Recipe Example:", fg="green", bold=True)
    click.echo("-" * 40)

    if meta.get("stage") in ["pre", "file"]:
        click.echo("  # Attached to a specific module:")
        click.echo("  modules:")
        click.echo("    - module: example_source")
        click.echo("      hooks:")
        click.echo(f"        - name: {name}")
    else:
        click.echo("  # Placed in the global pipeline:")
        click.echo("  global_hooks:")
        click.echo(f"    - name: {name}")

    if args_dict:
        click.echo("      args:")
        for key, val in args_dict.items():
            val_str = (
                f"{val['default']}"
                if isinstance(val["default"], str) and val != "REQUIRED"
                else val["default"]
            )
            click.echo(f"        {key}: {val_str}")

    click.echo("-" * 40 + "\n")


hooks_group.add_command(presets_group, name="presets")
