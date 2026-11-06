#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.cli
~~~~~~~~~~~~~~~~

Utility functions for terminals and cli.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import logging
import click
from typing import Optional, List

from .logging import (
    colorize,
    ITALIC,
    MAGENTA,
    RST,
    FOOT,
    MID,
    ICE,
    OCEAN,
    LOW,
    BOLD,
    GREEN,
    CYAN,
    HIGH,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Terminal Printing Helpers
# =============================================================================
def _cli_logo(name="fetchez", desc="", version=""):
    """Prints a colored ANSI block representation of the Fetchez logo."""

    # logo = f"""
    # {LOW}  {RST}{MID}  {RST}{FOOT}  {RST}{HIGH}  {RST}{MID}  {RST}
    # {OCEAN}  {RST}{LOW}  {RST}{HIGH}  {RST}{MID}  {RST}{FOOT}  {RST}   {colorize(name, MAGENTA)} {version}
    # {MID}  {RST}{OCEAN}  {RST}{MID}  {RST}{ICE}  {RST}{ICE}  {RST}   {colorize(desc, ITALIC)}
    # """
    logo = f"""
    {LOW}  {RST}{MID}  {RST}{FOOT}  {RST}  {colorize(name, MAGENTA)} {version}
    {OCEAN}  {RST}{ICE}  {RST}{HIGH}  {RST}  {colorize(desc, ITALIC)}
    """

    return logo


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
