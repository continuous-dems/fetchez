#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
from fetchez.cli.utils import (
    filter_registry,
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
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

    pass


@modifiers_group.command("list", cls=FetchezMainCommand)
@click.option(
    "--group-by",
    type=click.Choice(["provider", "category"]),
    default="provider",
    help="Group results by type.",
)
@click.option("--search", help="Filter bundles by name or keyword.")
@click.option(
    "--provider",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
def list_modifiers(group_by, search, provider):
    """List all available built-in and local recipe modifiers."""

    registry = search_modifiers(search)
    registry = filter_registry(
        registry,
        {
            "provider": provider,
        },
    )

    group_key = "provider" if group_by == "provider" else group_by
    grouped_modifiers = group_registry_by_key(registry, group_key)
    print_grouped_registry(grouped_modifiers, "Modifiers", "Category")
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
