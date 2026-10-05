#!/usr/bin/env python

"""
fetchez.cli.streams.readers
~~~~~~~~~~~~~~~~

Discoverability and documentation for stream readers.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys

import click

from fetchez.api import search_readers
from fetchez.registry import ProfileRegistry, ReaderRegistry
from fetchez.utils import (
    FetchezMainCommand,
    FetchezMainGroup,
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
)


@click.group(
    cls=FetchezMainGroup,
    name="readers",
    fetchez_commands=["list", "info", "update-cache"],
)
def readers_group():
    """Discover, search, and learn about stream format readers.

    \b
    Readers are the underlying Python classes (like 'rasterio-point-reader' or
    'csvreader') that open downloaded files and convert them into standard
    streams or chunks for processing.

    \b
    Usage:
      You rarely call Readers directly. They are automatically triggered by the
      `stream-init` hook based on the file extension or the data's 'Profile',
      defined by the modules' entry['data_type'].

    \b
      Format reader streams can be initiated with the `stream-init` hook which
      will populate entry['stream'] and entry['stream-type'] in the pipeline.
    """


@readers_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter readers by name or keyword.")
def readers_list(search):
    """List all available stream readers grouped by category."""

    registry = search_readers(search)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Stream Readers", "Provider")
    click.echo(
        "\nRun 'fetchez streams readers info <name>' for arguments and recipe examples.\n"
    )


@readers_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def readers_info(name):
    """Show arguments and YAML recipe examples for a specific reader."""

    ReaderRegistry.load_all()
    schema_cls = ReaderRegistry.get_class(name)
    meta = ReaderRegistry.get_info(name)

    if not schema_cls:
        click.secho(f"Error: Reader '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n🌐 READER: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}\n")

    # print_class_arguments(schema_cls)
    args_dict = get_class_arguments(schema_cls)
    if args_dict:
        click.secho("  Arguments:", fg="yellow", bold=True)
        for key, val in args_dict.items():
            click.echo(f"    - {click.style(key, bold=True)} {val['default']}")

    ProfileRegistry.load_all()
    profile_registry = ProfileRegistry.get_registry()
    click.secho("\n  Available Profiles:", fg="yellow", bold=True)
    for profile in profile_registry:
        profile_meta = ProfileRegistry.get_yaml(profile)
        profile_reader = profile_meta.get("reader").get("name")
        if profile_reader == name:
            click.echo(f"    - {click.style(profile_meta.get('name'), bold=True)}")

    click.echo("\n" + "-" * 40 + "\n")
