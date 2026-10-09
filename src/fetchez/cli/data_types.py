#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.data_types
~~~~~~~~~~~~~~~~

Discoverability and documentation for fetchez data_types.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import yaml
import click
from pathlib import Path

from fetchez.registry import DataTypeRegistry
from fetchez.utils import (
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.api import search_data_types
from .detectors import detectors_group


@click.group(
    cls=FetchezMainGroup,
    name="datatypes",
    fetchez_commands=["dump", "copy", "info", "list", "detectors"],
)
def data_types_group():
    """Discover and inspect Fetchez entry Data Types.

    \b
    DataTypes in Fetchez describe the various types of data that
    are discovered and returnd from Fetchez Modules.
    """

    pass


@data_types_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter data type by name or keyword.")
def list_data_types(search):
    """List all available built-in and local data types."""

    registry = search_data_types(search)
    grouped_hooks = group_registry_by_key(registry, "category")
    print_grouped_registry(grouped_hooks, "Entry Data Types", "Category")
    click.echo("\nRun 'fetchez datatypes info <name>' for more information.\n")


@data_types_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def info_data_types(name):
    """Print a clean, readable summary of a Data Type."""

    DataTypeRegistry.load_all()
    meta = DataTypeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Data Type '{name}' not found.", fg="red")
        sys.exit(1)

    click.echo(meta)
    click.secho(f"\n📜 DATA TYPE SUMMARY: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('description', 'N/A').strip()}")

    click.echo("\n" + "=" * 60 + "\n")


@data_types_group.command("dump", cls=FetchezMainCommand)
@click.argument("name")
def dump_data_types(name):
    """Print the raw YAML definition to the terminal."""

    DataTypeRegistry.load_all()
    meta = DataTypeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Data Type '{name}' not found.", fg="red")
        sys.exit(1)

    # Dump the dictionary back to a formatted YAML string
    yaml_str = yaml.dump(meta, sort_keys=False)

    click.secho(f"--- # {name}.yaml", fg="bright_black")
    click.echo(yaml_str)


@data_types_group.command("copy", cls=FetchezMainCommand)
@click.argument("name")
def copy_data_type(name):
    """Copy a datatype to your local ~/.fetchez/ folder for editing."""

    DataTypeRegistry.load_all()
    meta = DataTypeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Data Type '{name}' not found.", fg="red")
        sys.exit(1)

    # Use the registry's built-in user folder mapping!
    user_dir = Path(f"~/.fetchez/{DataTypeRegistry.user_folder}").expanduser()
    user_dir.mkdir(parents=True, exist_ok=True)

    out_path = user_dir / f"{name}.yaml"

    if out_path.exists():
        click.secho(f"⚠️ File already exists: {out_path}", fg="yellow")
        click.confirm("Do you want to overwrite it?", abort=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(yaml.dump(meta, sort_keys=False))

    click.secho(f"\n✅ Copied '{name}' to {out_path}", fg="green", bold=True)
    click.echo("Fetchez will now prioritize this local file over the built-in version!")
    click.echo("You can open it in any text editor to safely customize the pipeline.\n")


data_types_group.add_command(detectors_group, name="detectors")
