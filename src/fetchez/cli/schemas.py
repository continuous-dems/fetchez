#!/usr/bin/env python

"""
fetchez.cli.schemas
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing schemas.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys

import click

from fetchez.api import search_schemas
from fetchez.registry import SchemaRegistry
from fetchez.utils import (
    FetchezMainCommand,
    FetchezMainGroup,
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
)


@click.group(
    cls=FetchezMainGroup,
    name="schemas",
    fetchez_commands=["list", "info", "update-cache"],
)
def schemas_group():
    """Discover, search, and learn about recipe schemas.

    \b
    Schemas are strict validation rulesets that can be applied to Recipes.
    They ensure that any data flowing through the pipeline adheres to specific
    domain standards (e.g., forcing all output to be in EPSG:4326, or requiring
    mandatory metadata tags).
    """


@schemas_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter schemas by name or keyword.")
def schemas_list(search):
    """List all available processing schemas grouped by category."""

    registry = search_schemas(search)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Schemas", "Provider")
    click.echo(
        "\nRun 'fetchez recipes schemas info <name>' for arguments and recipe examples.\n"
    )


@schemas_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def schemas_info(name):
    """Show arguments and YAML recipe examples for a specific hook."""

    SchemaRegistry.load_all()
    schema_cls = SchemaRegistry.get_class(name)
    meta = SchemaRegistry.get_info(name)

    if not schema_cls:
        click.secho(f"Error: Schema '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n🏛️ SCHEMA: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}\n")

    # print_class_arguments(schema_cls)
    args_dict = get_class_arguments(schema_cls)
    if args_dict:
        click.secho("  Arguments:", fg="yellow", bold=True)
        for key, val in args_dict.items():
            click.echo(f"    - {click.style(key, bold=True)} {val['default']}")

    # Generate the YAML Snippet
    click.secho("\n  YAML Recipe Example:", fg="green", bold=True)
    click.echo("-" * 40)

    click.echo(f"schema: {name}")

    click.echo("-" * 40 + "\n")
