#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.utils
~~~~~~~~~~~~~~~~~~

CLI-only helpers for Fetchez command formatting and registry discovery.

No registry loading or mutations happen here. Functions consume normalized
registry metadata dictionaries, with a meta_* fallback for transitional use.
"""

from __future__ import annotations

import inspect
import shutil
from collections.abc import Mapping
from typing import Optional, List

import click

from fetchez.utils import colorize, GREEN, CYAN, BOLD, RED


class FetchezMainGroup(click.Group):
    """Custom group to categorize the main CLI commands."""

    def __init__(self, fetchez_commands: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)

        self.fetchez_commands = fetchez_commands or []

    def format_usage(self, ctx, formatter):
        usage_pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(
            ctx.command_path,
            " ".join(usage_pieces),
            prefix=f"{colorize(colorize('Usage: ', GREEN), BOLD)}",
        )

    def format_options(self, ctx, formatter):
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                rv = (f"{colorize(colorize(rv[0], CYAN), BOLD):<30}", rv[1])
                opts.append(rv)

        if opts:
            with formatter.section(f"{colorize(colorize('Options', GREEN), BOLD)}"):
                formatter.write_dl(opts)

        self.format_commands(ctx, formatter)

    def format_commands(self, ctx, formatter):
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        if isinstance(self.fetchez_commands, dict):
            categories = {
                f"{colorize(colorize(k, GREEN), BOLD)}": v
                for k, v in self.fetchez_commands.items()
            }
        else:
            categories = {
                f"{colorize(colorize('Commands', GREEN), BOLD)}": self.fetchez_commands,
            }

        for cat_name, cmd_names in categories.items():
            with formatter.section(cat_name):
                cat_cmds = [
                    (
                        f"{colorize(colorize(name, CYAN), BOLD):<30}",
                        cmd.get_short_help_str(),  # limit=80
                    )
                    for name, cmd in commands
                    if name in cmd_names
                ]
                formatter.write_dl(cat_cmds)


class FetchezMainCommand(click.Command):
    """Custom command to colorize the main CLI commands."""

    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)

    def format_usage(self, ctx, formatter):
        usage_pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(
            ctx.command_path,
            " ".join(usage_pieces),
            prefix=f"{colorize(colorize('Usage: ', GREEN), BOLD)}",
        )

    def format_options(self, ctx, formatter):
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                rv = (f"{colorize(colorize(rv[0], CYAN), BOLD)}", rv[1])
                opts.append(rv)

        if opts:
            with formatter.section(f"{colorize(colorize('Options', GREEN), BOLD)}"):
                formatter.write_dl(opts)


def registry_meta(meta, key, default=None):
    """Read normalized registry metadata, with a meta_* fallback."""
    if not isinstance(meta, Mapping):
        return default
    if key in meta:
        return meta[key]
    if key.startswith("meta_"):
        return meta.get(key, default)
    return meta.get(f"meta_{key}", default)


def registry_values(meta, key):
    """Return a scalar or sequence-valued field as a list."""
    value = registry_meta(meta, key)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def registry_provider(meta):
    """Determine discovery provider from explicit metadata or Python module path."""
    explicit = registry_meta(meta, "provider")
    if explicit:
        return str(explicit).strip().casefold()
    module = str(registry_meta(meta, "mod", "") or "").strip()
    root = module.split(".", 1)[0].casefold()
    if root == "fetchez":
        return "builtin"
    if root in {"fetchez_user", "user"}:
        return "user"
    return root or "unknown"


def _registry_items(registry):
    return registry.items() if isinstance(registry, Mapping) else registry


def _is_alias(name, meta):
    # Preserve the existing registry convention for suppressing alias entries.
    return str(name).split(".")[-1] in {
        str(alias) for alias in registry_values(meta, "aliases")
    }


def filter_registry(registry, filters=None):
    """AND fields, OR repeated values per field; comparisons are case-insensitive.

    Empty filters are ignored. A provider filter uses registry provenance.
    """
    filters = filters or {}
    filtered = {}
    for name, meta in _registry_items(registry):
        for key, wanted in filters.items():
            if wanted is None or wanted == "" or wanted == () or wanted == []:
                continue
            requested = (
                list(wanted)
                if isinstance(wanted, (list, tuple, set, frozenset))
                else [wanted]
            )
            values = (
                [registry_provider(meta)]
                if key == "provider"
                else registry_values(meta, key)
            )
            if not any(
                str(v).casefold() == str(w).casefold()
                for v in values
                for w in requested
            ):
                break
        else:
            filtered[name] = meta
    return filtered


def group_registry_by_key(registry, key="category"):
    """Group by scalar or multi-valued metadata, retaining old call signature.

    An item with multiple effects appears under each effect. Missing fields
    are grouped as Unspecified; provider/mod groups normalize user/builtin.
    """
    grouped = {}
    for name, meta in _registry_items(registry):
        if _is_alias(name, meta):
            continue
        if key in {"provider", "mod"}:
            values = [registry_provider(meta)]
        else:
            values = registry_values(meta, key) or ["Unspecified"]
        for value in values:
            label = str(value)
            if key in {"provider", "mod"}:
                label = label.title()
            grouped.setdefault(label, []).append((name, meta))
    return grouped


def truncate_string(input_string: str, padding: int = 0):
    """Truncate text to the current terminal width, safely on narrow terminals."""
    width = max(4, shutil.get_terminal_size(fallback=(100, 24)).columns - padding)
    value = str(input_string)
    return value if len(value) <= width else value[: width - 3] + "..."


def print_grouped_registry(
    grouped_hooks, registry_type="Modules", key="Provider", display_key="category"
):
    """Print registry groups; first three arguments remain backward compatible."""
    click.secho(f"\nAvailable {registry_type} by {key}:", fg="cyan", bold=True)
    click.echo("=" * 60)
    if not grouped_hooks:
        click.echo("  No matching components.")
        return
    for group in sorted(grouped_hooks, key=str.casefold):
        click.secho(f"\n[ {group} ]", fg="yellow", bold=True)
        for name, meta in sorted(
            grouped_hooks[group], key=lambda item: item[0].casefold()
        ):
            values = registry_values(meta, display_key) if display_key else []
            secondary = ", ".join(map(str, values)) if values else "Unspecified"
            desc = (
                registry_meta(meta, "desc")
                or registry_meta(meta, "description")
                or "No description provided."
            )
            desc = (
                str(desc).strip().splitlines()[0]
                if str(desc).strip()
                else "No description provided."
            )
            name_text = f"{name:<26}"
            secondary_text = f"[{secondary[:18]:^18}]" if display_key else ""
            padding = len(name_text) + len(secondary_text) + 7
            click.echo(
                f"  {click.style(name_text, bold=True, fg='green')} "
                f"{click.style(secondary_text, fg='blue')} : {truncate_string(desc, padding)}"
            )


def get_class_arguments(TargetCls, want_inherited=True):
    """Inspect a class for arguments and print them out."""

    all_params = {}
    for cls in TargetCls.__mro__:
        if cls is object:
            continue

        if hasattr(cls, "__init__"):
            try:
                sig = inspect.signature(cls.__init__)
                for name, param in sig.parameters.items():
                    if name == "self" or param.kind in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    ):
                        continue

                    if name not in all_params:
                        all_params[name] = {"param": param, "origin": cls}
            except ValueError:
                pass

    args_dict = {}
    if all_params:
        arg_help = getattr(TargetCls, "_cli_arg_help", {})
        for name, data in all_params.items():
            param = data["param"]
            origin_cls = data["origin"]
            origin_help = getattr(origin_cls, "_cli_arg_help", {})

            if param.default is inspect.Parameter.empty:
                default_str = colorize("(required)", RED)
            else:
                # default_str = f"(default: {param.default or 'None'})"
                default_str = param.default  # or None  # or 'None'}"

            type_str = ""
            if param.annotation is not inspect.Parameter.empty:
                type_name = getattr(param.annotation, "__name__", str(param.annotation))
                type_str = f"[{type_name}] "

            inherit_str = ""
            if origin_cls is not TargetCls:
                inherit_str = colorize(f" [from {origin_cls.__name__}]", CYAN)
                desc_str = f" - {origin_help[name]}" if name in origin_help else ""
            else:
                desc_str = f" - {arg_help[name]}" if name in arg_help else ""

            args_dict[name] = {
                "type": type_str,
                "default": default_str,
                "inherit": inherit_str,
                "desc": desc_str,
            }

    return args_dict
