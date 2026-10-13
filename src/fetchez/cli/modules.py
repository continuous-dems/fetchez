#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.modules
~~~~~~~~~~~~~~~~

Discoverability and documentation for fetching modules.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click
import sys
from fetchez.api import search_modules
from fetchez.registry import ModuleRegistry
from fetchez.cli.utils import (
    filter_registry,
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from .bundles import bundles_group

MODULES_COMMANDS = ["info", "list", "search", "bundles", "update-cache"]


@click.group(
    cls=FetchezMainGroup,
    name="modules",
    fetchez_commands=MODULES_COMMANDS,
)
def modules_group():
    """Discover, search, and learn about data sources.

    \b
    Modules are the starting point of any Fetchez pipeline. They are responsible
    for discovering and downloading data from remote agencies (like NOAA, USGS,
    Copernicus) or loading it from your local file system.

    \b
    This command group lets you explore and run the available Data 'Modules' and
    'Bundles' that give access to geospatial data around the world.
    """

    pass


@modules_group.command("search", cls=FetchezMainCommand)
@click.argument("term")
def module_search(term):
    """Search all available modules by keyword."""

    registry = search_modules(term)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Modules", "Provider")
    click.echo(
        "\nRun 'fetchez modules info <name>' for arguments and recipe examples.\n"
    )


@modules_group.command("list", cls=FetchezMainCommand)
@click.option(
    "--group-by",
    type=click.Choice(
        ["provider", "category", "agency", "region", "resolution", "license"]
    ),
    default="provider",
    help="Group results by type.",
)
@click.option("--search", help="Filter results by search term.")
@click.option(
    "--provider",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
@click.option("--agency", multiple=True, help="Filter results by agency.")
@click.option("--region", multiple=True, help="Filter results by region.")
@click.option("--resolution", multiple=True, help="Filter results by resolution.")
@click.option("--license", multiple=True, help="Filter results by license.")
def module_list(group_by, search, provider, agency, region, resolution, license):
    """List all available modules grouped by category."""

    registry = search_modules(search)

    registry = filter_registry(
        registry,
        {
            "provider": provider,
            "agency": agency,
            "region": region,
            "resolution": resolution,
            "license": license,
        },
    )

    group_key = "provider" if group_by == "provider" else group_by

    grouped_modules = group_registry_by_key(registry, group_key)
    print_grouped_registry(grouped_modules, "Modules", group_by.title())
    click.echo(
        "\nRun 'fetchez modules info <name>' for arguments and recipe examples.\n"
    )


@modules_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def module_info(name):
    """Get detailed metadata and available CLI arguments for a module."""

    ModuleRegistry.load_all()
    meta = ModuleRegistry.get_info(name)
    mod_cls = ModuleRegistry.get_class(name)

    if not meta or not mod_cls:
        click.secho(f"Error: Module '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n📦 MODULE: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}")
    click.echo(f"  Agency      : {meta.get('agency', 'N/A')}")
    click.echo(f"  Resolution  : {meta.get('resolution', 'N/A')}")
    click.echo(f"  License     : {meta.get('license', 'N/A')}")

    tags = meta.get("tags", [])
    if tags:
        click.echo(f"  Tags        : {', '.join(tags)}")

    urls = meta.get("urls", {})
    if urls:
        click.echo("\n  Links:")
        for link_name, link_url in urls.items():
            click.echo(f"    - {link_name.title()}: {link_url}")

    # args_dict = get_class_arguments(mod_cls)
    args_dict = get_class_arguments(mod_cls)
    click.secho("\n  Arguments:", fg="yellow", bold=True)
    for key, val in args_dict.items():
        click.echo(
            f"    - {click.style(key, bold=True)} {val['type']}[{val['default']}]{val['inherit']}{val['desc']}"
        )

    # Generate the YAML Snippet
    click.secho("\n  YAML Recipe Example:", fg="green", bold=True)
    click.echo("-" * 40)

    click.echo("  modules:")
    click.echo(f"    - module: {name}")

    if args_dict:
        click.echo("      args:")
        for key, val in args_dict.items():
            val_str = (
                f"{val['default']}"
                if isinstance(val["default"], str) and val["default"] != "REQUIRED"
                else val["default"]
            )
            click.echo(f"        {key}: {val_str}")

        # click.echo("      hooks:")
    click.echo("-" * 40 + "\n")


modules_group.add_command(bundles_group, name="bundles")
