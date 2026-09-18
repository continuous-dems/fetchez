#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.presets
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing macros (presets).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import yaml
import click
from pathlib import Path

from fetchez.api import search_presets
from fetchez.registry import PresetRegistry
from fetchez.utils import (
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.recipe import Recipe


@click.group(
    cls=FetchezMainGroup,
    name="presets",
    fetchez_commands=["copy", "dump", "info", "list"],
)
def presets_group():
    """Discover, inspect, and copy processing macros.

    \b
    Presets are YAML macros that chain multiple processing Hooks together
    under a single name. If you frequently run the exact same sequence of
    filters, you can save them as a Preset and call them with one word.

    \b
    Usage:
      Presets act exactly like Hooks. You can pass them to `--hook`, `--global-hook`,
      or list them in your Recipe's hook list.
    """
    # As such, Presets can reference other Presets as well as Hooks.
    pass


def print_grouped_presets(grouped_hooks, key="Provider"):
    click.secho(f"\nAvailable Presets by {key}:", fg="cyan", bold=True)
    click.echo("=" * 60)

    for cat in sorted(grouped_hooks.keys()):
        click.secho(f"\n[ {cat} ]", fg="yellow", bold=True)
        for name, meta in sorted(
            grouped_hooks[cat], key=lambda x: x[0]
        ):  # x: x[1].get("category")):
            category = meta.get(
                "category", meta.get("Category", "Uncategorized")
            ).title()
            desc = meta.get("desc", meta.get("description", "No description provided."))

            name_padded = f"{name:<26}"
            category_padded = f"[{category:^18}]"

            click.echo(
                f"  {click.style(name_padded, bold=True, fg='green')} {click.style(category_padded, fg='blue')} : {desc}"
            )
    click.echo("\nRun 'fetchez hooks info <name>' for arguments and recipe examples.\n")


@presets_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter presets by name or keyword.")
def list_presets(search):
    """List all available built-in and local presets."""

    registry = search_presets(search)
    grouped_presets = group_registry_by_key(registry, "provider")
    print_grouped_registry(grouped_presets, "Presets", "Provider")
    click.echo(
        "\nRun 'fetchez hooks presets info <name>' for arguments and recipe examples.\n"
    )


@presets_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def info_preset(name):
    """Print a clean, readable summary of a preset's contents."""

    PresetRegistry.load_all()
    meta = PresetRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Preset '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n📜 PRESET SUMMARY: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('description', 'N/A').strip()}")

    hooks = meta.get("hooks", [])
    hooks = Recipe({})._expand_hooks(hooks)
    if hooks:
        click.echo(f"\n  Hooks ({len(hooks)}):")
        for hook in hooks:
            hook_name = hook.get("name")
            click.echo(f"    - {click.style(hook_name, fg='green')}")
            for arg in hook.get("args", []):
                click.echo(
                    f"     ⤷ {click.style(arg, fg='cyan')}: {hook.get('args').get(arg)}"
                )

    click.echo("=" * 60 + "\n")


@presets_group.command("dump", cls=FetchezMainCommand)
@click.argument("name")
def dump_preset(name):
    """Print the raw YAML definition to the terminal."""

    PresetRegistry.load_all()
    meta = PresetRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Preset '{name}' not found.", fg="red")
        sys.exit(1)

    # Dump the dictionary back to a formatted YAML string
    yaml_str = yaml.dump(meta, sort_keys=False)

    click.secho(f"--- # {name}.yaml", fg="bright_black")
    click.echo(yaml_str)


@presets_group.command("copy", cls=FetchezMainCommand)
@click.argument("name")
def copy_preset(name):
    """Copy a preset to your local ~/.fetchez/ folder for editing."""

    PresetRegistry.load_all()
    meta = PresetRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Preset '{name}' not found.", fg="red")
        sys.exit(1)

    # Use the registry's built-in user folder mapping!
    user_dir = Path(f"~/.fetchez/{PresetRegistry.user_folder}").expanduser()
    user_dir.mkdir(parents=True, exist_ok=True)

    out_path = user_dir / f"{name}.yaml"

    if out_path.exists():
        click.secho(f"⚠️  File already exists: {out_path}", fg="yellow")
        click.confirm("Do you want to overwrite it?", abort=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(yaml.dump(meta, sort_keys=False))

    click.secho(f"\n✅ Copied '{name}' to {out_path}", fg="green", bold=True)
    click.echo("Fetchez will now prioritize this local file over the built-in version!")
    click.echo("You can open it in any text editor to safely customize the pipeline.\n")
