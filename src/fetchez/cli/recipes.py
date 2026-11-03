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
import json
import yaml
import click
from pathlib import Path

from fetchez.recipe import Recipe, load_recipe_config
from fetchez.registry import RecipeRegistry
from fetchez.cli.utils import (
    filter_registry,
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.api import search_recipes
from .schemas import schemas_group
from .modifiers import modifiers_group

RECIPE_COMMANDS = [
    "compile",
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
    recipes.
    """

    pass


@recipes_group.command("list", cls=FetchezMainCommand)
@click.option(
    "--group-by",
    type=click.Choice(["provider", "category"]),
    default="provider",
    help="Group results by type.",
)
@click.option("--search", help="Filter results by search term.")
@click.option(
    "--provider",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
def list_recipes(group_by, search, provider):
    """List all available built-in and local recipes."""

    registry = search_recipes(search)

    registry = filter_registry(
        registry,
        {
            "provider": provider,
        },
    )
    group_key = "provider" if group_by == "provider" else group_by

    grouped_recipes = group_registry_by_key(registry, group_key)
    print_grouped_registry(grouped_recipes, "Recipes", group_by.title())
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


def _compile_label(definition, key):
    """Display a declarative or runtime component without copying its state."""
    if isinstance(definition, dict):
        definition = definition.get(key, "Unknown")
    if isinstance(definition, str):
        return definition
    if isinstance(definition, type):
        return definition.__name__
    return getattr(definition, "name", type(definition).__name__)


def _inspectable(value):
    """Convert a compiled definition into safe-to-encode presentation data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _inspectable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_inspectable(item) for item in value]
    if isinstance(value, type):
        return f"<class {value.__module__}.{value.__qualname__}>"
    # Avoid serializing arbitrary live instances (e.g., file handles and queues).
    return f"<instance {type(value).__module__}.{type(value).__qualname__}>"


def _print_compile_hook(hook, *, indent, verbose):
    name = _compile_label(hook, "name")
    click.echo(f"{' ' * indent}- {name}")
    if verbose and isinstance(hook, dict):
        for key, value in hook.get("args", {}).items():
            click.echo(f"{' ' * (indent + 2)}{key}: {_inspectable(value)}")


@recipes_group.command("compile", cls=FetchezMainCommand)
@click.argument("name")
@click.option(
    "--region",
    "region_override",
    default=None,
    help="Override the recipe region; useful for recipes with multiple regions.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["summary", "yaml", "json"], case_sensitive=False),
    default="summary",
    show_default=True,
    help="Output a readable execution plan or the fully resolved configuration.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show configured arguments in the readable summary.",
)
def compile_recipe(name, region_override, output_format, verbose):
    """Resolve and inspect a recipe without fetching or processing data.

    \b
    NAME may be a registered recipe or a local YAML/JSON recipe path.
    Expansion, modifiers, schema validation, and component initialization
    happen just as they would during execution. No pipeline is executed.

    \b
    Examples:
      fetchez recipes compile socal-crm-standard
      fetchez recipes compile ./recipe.yaml --region=-123/-122/36/37
      fetchez recipes compile ./recipe.yaml --format yaml
    """
    path = Path(name).expanduser()
    try:
        if path.is_file():
            recipe = Recipe.from_file(path)
        else:
            config = load_recipe_config(name)
            if config is None:
                raise click.ClickException(
                    f"Recipe '{name}' was not found locally or in the registry."
                )
            recipe = Recipe.from_dict(config)

        # Never modify the recipe's original configuration.
        if region_override is not None:
            recipe.config = {**recipe.config, "region": region_override}

        declared_modifiers = list(recipe.config.get("modifiers", []))
        declared_schemas = list(recipe.config.get("schemas", []))
        plan = recipe.compile()
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Could not compile '{name}': {exc}") from exc

    config = _inspectable(plan.config)
    if output_format == "json":
        click.echo(json.dumps(config, indent=2, ensure_ascii=False))
        return
    if output_format == "yaml":
        click.echo(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
        return

    click.secho(f"\nCOMPILED RECIPE: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"Project : {config.get('project', {}).get('name', recipe.name)}")
    click.echo(f"Region  : {config.get('region', 'Global / unspecified')}")
    click.echo(f"Threads : {plan.threads}")
    click.echo(f"Modules : {len(plan.modules)}")
    click.echo(f"Hooks   : {len(plan.global_hooks)} global")

    click.secho("\nModifiers requested:", fg="yellow", bold=True)
    if declared_modifiers:
        for item in declared_modifiers:
            click.echo(f"  - {_compile_label(item, 'name')}")
    else:
        click.echo("  (none)")

    click.secho("\nSchemas requested (validation passed):", fg="yellow", bold=True)
    if declared_schemas:
        for item in declared_schemas:
            click.echo(f"  - {_compile_label(item, 'name')}")
    else:
        click.echo("  (none)")

    click.secho("\nResolved data modules:", fg="green", bold=True)
    for definition in config.get("modules", []):
        click.echo(f"  - {_compile_label(definition, 'module')}")
        if isinstance(definition, dict):
            if verbose:
                for key, value in definition.get("args", {}).items():
                    click.echo(f"      {key}: {value}")
            for hook in definition.get("hooks", []):
                _print_compile_hook(hook, indent=6, verbose=verbose)
    if not config.get("modules"):
        click.echo("  (none)")

    click.secho("\nResolved global hooks (configured order):", fg="green", bold=True)
    for hook in config.get("global_hooks", []):
        _print_compile_hook(hook, indent=2, verbose=verbose)
    if not config.get("global_hooks"):
        click.echo("  (none)")

    click.echo("=" * 60)
    click.echo("Compilation successful. No pipeline was executed.\n")


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
