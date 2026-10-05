#!/usr/bin/env python

"""
fetchez.cli.modifiers
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing modifiers.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys

import click

from fetchez.api import search_modifiers
from fetchez.registry import ModifierRegistry
from fetchez.utils import (
    FetchezMainCommand,
    FetchezMainGroup,
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
)


@click.group(
    cls=FetchezMainGroup,
    name="modifiers",
    fetchez_commands=["list", "info", "update-cache"],
)
def modifiers_group():
    """Discover, search, and learn about recipe modifiers.

    \b
    Modifiers are middle-ware mutators that can be applied to Recipes.
    They can be used to make on-the-fly modifications to recipes before
    they are run.
    """


@modifiers_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter modifiers by name or keyword.")
def modifiers_list(search):
    """List all available processing modifiers grouped by category."""

    registry = search_modifiers(search)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Modifiers", "Provider")
    click.echo(
        "\nRun 'fetchez recipes modifiers info <name>' for arguments and recipe examples.\n"
    )


@modifiers_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def modifiers_info(name):
    """Show arguments and YAML recipe examples for a specific hook."""

    ModifierRegistry.load_all()
    modifier_cls = ModifierRegistry.get_class(name)
    meta = ModifierRegistry.get_info(name)

    if not modifier_cls:
        click.secho(f"Error: Modifier '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n🪝 MODIFIER: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}\n")

    # print_class_arguments(modifier_cls)
    args_dict = get_class_arguments(modifier_cls)
    if args_dict:
        click.secho("  Arguments:", fg="yellow", bold=True)
        for key, val in args_dict.items():
            click.echo(f"    - {click.style(key, bold=True)} {val['default']}")

    # Generate the YAML Snippet
    click.secho("\n  YAML Recipe Example:", fg="green", bold=True)
    click.echo("-" * 40)

    click.echo(f"modifier: {name}")

    click.echo("-" * 40 + "\n")
