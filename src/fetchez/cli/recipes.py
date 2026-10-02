#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.recipes
~~~~~~~~~~~~~~~~

Discoverability and documentation for fetchez recipes.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import yaml
import click
from pathlib import Path

from fetchez.recipe import Recipe, load_recipe_config
from fetchez.registry import RecipeRegistry
from fetchez.utils import (
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.api import search_recipes
from .schemas import schemas_group
from .modifiers import modifiers_group

RECIPE_COMMANDS = [
    "copy",
    "dump",
    "info",
    "list",
    "validate",
    "modifiers",
    "schemas",
    "translate",
]


@click.group(
    cls=FetchezMainGroup,
    name="recipes",
    fetchez_commands=RECIPE_COMMANDS,
)
def recipes_group():
    """Discover, inspect, validate, and manage complete pipeline recipes.

    \b
    Recipes are YAML definitions of complete Fetchez workflows, including
    project metadata, data modules and bundles, processing hooks, and execution
    settings.

    \b
    Use `fetchez recipes list` and `fetchez recipes info` to discover available
    recipes, or `fetchez run <recipe>` to execute one.
    """

    pass


@recipes_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Search by name, description, or tag.")
def list_recipes(search):
    """List all available built-in and local recipes."""

    registry = search_recipes(search)
    grouped_hooks = group_registry_by_key(registry, "provider")
    print_grouped_registry(grouped_hooks, "Recipes", "Provider")
    click.echo(
        "\nRun 'fetchez recipes info <name>' for arguments and recipe examples.\n"
    )


@recipes_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def info_recipe(name):
    """Print a clean, readable summary of a recipe's contents."""

    from fetchez.recipe import Recipe

    RecipeRegistry.load_all()
    meta = RecipeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Recipe '{name}' not found.", fg="red")
        sys.exit(1)

    # project = meta.get("project", {})
    click.secho(f"\n📜 RECIPE SUMMARY: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A').strip()}")

    config = meta.get("config", {})
    modules = Recipe({})._expand_modules(config.get("modules", []))
    if modules:
        click.echo(f"\n  Data Sources ({len(modules)}):")
        for mod in modules:
            mod_name = mod.get("module") or mod.get("bundle") or "Unknown"
            click.echo(f"    + {click.style(mod_name, fg='green')}")
            for arg in mod.get("args"):
                click.echo(
                    f"     ⤷ {click.style(arg, fg='cyan')}: {mod.get('args').get(arg)}"
                )

    # global_hooks = config.get("global_hooks", [])
    global_hooks = Recipe({})._expand_hooks(config.get("global_hooks", []))
    if global_hooks:
        click.echo(f"\n  Global Pipeline Steps ({len(global_hooks)}):")
        for hook in global_hooks:
            hook_name = hook.get("name") or hook.get("preset") or "Unknown"
            click.echo(f"    - {click.style(hook_name, fg='yellow')}")
            for arg in hook.get("args", []):
                click.echo(
                    f"     ⤷ {click.style(arg, fg='cyan')}: {hook.get('args').get(arg)}"
                )

    click.echo("=" * 60 + "\n")


@recipes_group.command("dump", cls=FetchezMainCommand)
@click.argument("name")
def dump_recipe(name):
    """Print the raw YAML definition to the terminal."""

    RecipeRegistry.load_all()
    meta = RecipeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Recipe '{name}' not found.", fg="red")
        sys.exit(1)

    # Dump the dictionary back to a formatted YAML string
    yaml_str = yaml.dump(meta, sort_keys=False)

    click.secho(f"--- # {name}.yaml", fg="bright_black")
    click.echo(yaml_str)


@recipes_group.command("copy", cls=FetchezMainCommand)
@click.argument("name")
def copy_recipe(name):
    """Copy a recipe to your local ~/.fetchez/ folder for editing."""

    RecipeRegistry.load_all()
    meta = RecipeRegistry.get_yaml(name)

    if not meta:
        click.secho(f"Error: Recipe '{name}' not found.", fg="red")
        sys.exit(1)

    # Use the registry's built-in user folder mapping!
    user_dir = Path(f"~/.fetchez/{RecipeRegistry.user_folder}").expanduser()
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


@recipes_group.command("validate", cls=FetchezMainCommand)
@click.argument("name")
@click.option(
    "--schema", multiple=True, help="Apply validation schemas (e.g., 'cudem')."
)
def recipe_validate(name, schema):
    """Check a recipe for syntax errors, logical issues, and missing dependencies."""

    base_config = load_recipe_config(name)
    if not base_config:
        click.secho(
            f"Error: Recipe '{name}' not found locally or in the registry.", fg="red"
        )
        sys.exit(1)

    click.secho(f"Validating {name}...", fg="blue")

    recipe_obj = Recipe.from_dict(base_config)
    recipe_config = recipe_obj.config
    recipe_config["modules"] = recipe_obj._expand_modules(
        recipe_obj.config.get("modules", [])
    )
    recipe_config["global_hooks"] = recipe_obj._expand_hooks(
        recipe_obj.config.get("global_hooks", [])
    )

    schema_defs = [{"name": x} for x in schema]
    schemas = recipe_obj._init_schemas(schema_defs)

    errors = []
    for schema in schemas:
        schema_name = click.style(schema.name, bold=True)
        click.secho(f"Validating against {schema_name} schema...", nl=False)
        _valid, _errors = schema.run(recipe_config)
        if not _valid:
            click.secho("FAIL", fg="red")
            errors.extend(_errors)
        else:
            click.secho("PASS", bg="green")

    is_valid = len(errors) == 0

    if is_valid:
        click.secho("Recipe appears valid!", fg="green", bold=True)
    else:
        click.secho(
            f"\n[ VALIDATION FAILED WITH {len(errors)} ERRORS ]", fg="red", bold=True
        )
        for error in errors:
            click.echo(f"  {error}")
        click.echo("\nPlease modify the recipe and try again.\n")
        sys.exit(1)


@recipes_group.command("translate", cls=FetchezMainCommand)
@click.argument("name")
@click.option(
    "--json", "as_json", is_flag=True, help="Convert the YAML recipe directly to JSON."
)
def translate_recipe(name, as_json):
    """Translate a YAML recipe into a fetchez CLI command string or JSON."""

    base_config = load_recipe_config(name)
    if not base_config:
        click.secho(
            f"Error: Recipe '{name}' not found locally or in the registry.", fg="red"
        )
        sys.exit(1)

    recipe_obj = Recipe.from_dict(base_config)

    if as_json:
        click.secho("\n--- JSON Recipe ---\n", fg="cyan", bold=True)
        click.echo(recipe_obj.to_json())
        click.echo("\n")
    else:
        click.secho("\n--- Translated CLI Command ---\n", fg="cyan", bold=True)
        click.echo(recipe_obj.to_cli())
        click.echo("\n")


recipes_group.add_command(schemas_group, name="schemas")
recipes_group.add_command(modifiers_group, name="modifiers")
