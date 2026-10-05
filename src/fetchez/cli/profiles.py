#!/usr/bin/env python

"""
fetchez.cli.profiles
~~~~~~~~~~~~~~~~

Discoverability and documentation for fetching profiles.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
from pathlib import Path

import click
import yaml

from fetchez.api import search_profiles
from fetchez.registry import ProfileRegistry
from fetchez.utils import (
    FetchezMainCommand,
    FetchezMainGroup,
    group_registry_by_key,
    print_grouped_registry,
)


@click.group(
    cls=FetchezMainGroup,
    name="profiles",
    fetchez_commands=["copy", "dump", "info", "list"],
)
def profiles_group():
    """Discover, inspect, and copy stream format profiles.

    \b
    Different datasets are formatted differently (e.g., one NetCDF uses 'lon'
    and 'lat', another uses 'x' and 'y'). Profiles are YAML dictionaries that
    tell a Reader exactly how to parse a specific dataset's format.
    """


@profiles_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter profiles by name or keyword.")
def list_profiles(search):
    """List all available built-in and local profiles."""

    registry = search_profiles(search)
    grouped_hooks = group_registry_by_key(registry, "provider")
    print_grouped_registry(grouped_hooks, "Stream Profiles", "Provider")
    click.echo(
        "\nRun 'fetchez streams profiles info <name>' for arguments and recipe examples.\n"
    )


@profiles_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def info_profiles(name):
    """Print a clean, readable summary of a bundle's contents."""

    ProfileRegistry.load_all()
    meta = ProfileRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Profile '{name}' not found.", fg="red")
        sys.exit(1)

    click.echo(meta)
    click.secho(f"\n📜 PROFILE SUMMARY: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('description', 'N/A').strip()}")

    reader = meta.get("reader")  # .get("name")

    if reader:
        click.secho("\n  Supported Reader:", fg="yellow", bold=True)
        click.echo(f"    - {click.style(reader.get('name'), fg='green')}")
        for arg in reader.get("args", []):
            click.echo(
                f"     ⤷ {click.style(arg, fg='cyan')}: {reader.get('args').get(arg)}"
            )

    click.echo("\n" + "=" * 60 + "\n")


@profiles_group.command("dump", cls=FetchezMainCommand)
@click.argument("name")
def dump_bundle(name):
    """Print the raw YAML definition to the terminal."""

    ProfileRegistry.load_all()
    meta = ProfileRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Profile '{name}' not found.", fg="red")
        sys.exit(1)

    # Dump the dictionary back to a formatted YAML string
    yaml_str = yaml.dump(meta, sort_keys=False)

    click.secho(f"--- # {name}.yaml", fg="bright_black")
    click.echo(yaml_str)


@profiles_group.command("copy", cls=FetchezMainCommand)
@click.argument("name")
def copy_bundle(name):
    """Copy a reader profile to your local ~/.fetchez/ folder for editing."""

    ProfileRegistry.load_all()
    meta = ProfileRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Profile '{name}' not found.", fg="red")
        sys.exit(1)

    # Use the registry's built-in user folder mapping!
    user_dir = Path(f"~/.fetchez/{ProfileRegistry.user_folder}").expanduser()
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
