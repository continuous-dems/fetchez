#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli
~~~~~~~~~~~

The main command-line interface for the Fetchez framework.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click
import logging
from typing import Optional

from fetchez.utils import TqdmLoggingHandler, FetchezMainGroup

from .pipeline import pipeline_group
from .modules import modules_group
from .hooks import hooks_group
from .recipes import recipes_group
from .streams import streams_group
from .data_types import data_types_group
from .regions import regions_group
from .cache import cache_group


# =============================================================================
# CLI Decorator and Decorations and logging
# =============================================================================
def cli_opts(help_text: Optional[str] = None, **arg_help):
    """Decorator to attach CLI help text to FetchModule classes.

    Args:
        help_text: The description for the module's sub-command.
        **arg_help: Key-value pairs matching __init__ arguments to help strings.
    """

    def decorator(cls):
        cls._cli_help_text = help_text
        cls._cli_arg_help = arg_help
        return cls

    return decorator


def setup_logging(name="fetchez", quiet=False, verbose=False):
    """Setup logging for the fetchez based clis"""

    if quiet:
        log_level = logging.WARNING
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = TqdmLoggingHandler()

    formatter = logging.Formatter("[ %(levelname)s ] %(module)s: %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)


@click.group(
    cls=FetchezMainGroup,
    # help=f"\b{_cli_logo('fetchez', 'Fetch geospatial data with ease.', __version__)}",
    fetchez_commands={
        "Pipeline": ["run"],
        "Discovery and Management": [
            "modules",
            "hooks",
            "recipes",
            "streams",
            "datatypes",
            "regions",
            "cache",
            "lavache",
        ],
    },
    # epilog="https://fetchez.readthedocs.io/en/latest/index.html"
)
@click.version_option(package_name="fetchez")
@click.option("--verbose", is_flag=True, help="Enable verbose debug logging.")
@click.option("--quiet", is_flag=True, help="Suppress non-error output.")
def cli(verbose, quiet):
    """Fetch geospatial data with ease.

    \b
    Fetchez is a streaming ETL pipeline for geospatial data.
    It allows you to download geospatial data from local or remote sources,
    pipe that data through processing hooks (like clipping or reprojecting),
    and save the results to disk. All in a single command or a YAML recipe.

    \b
    Core Concepts:
      1. Modules    : Data Sources (see `fetchez modules`)
      2. Hooks      : Processing Steps (see `fetchez hooks`)
      3. Streams    : Data Streaming (see `fetchez streams`)
      4. Recipes    : YAML pipeline definitions (see `fetchez recipes`)
      5. Pipelines  : Run full data processing pipelines (see `fetchez run`)
      6. Data Types : Entry Data Types (see `fetchez datatypes`)
    """
    # \b
    # Examples:
    #   # Quick fetch for a specific location
    #   $ fetchez run -R loc:seattle tides
    #   \b
    #   # Run multiple modules with weights and specific hooks
    #   $ fetchez run -R -120/34/-119/35 coned --weight 2.0 tnm --hook unzip
    #   \b
    #   # Execute a complete pre-built YAML pipeline recipe
    #   $ fetchez run --recipe crm_standard
    #   \b
    #   # Export a dynamic CLI command into a reusable YAML recipe
    #   $ fetchez run -R loc:hawaii --export my_pipeline.yaml bluetopo
    # """,

    setup_logging(quiet=quiet, verbose=verbose)


@click.command("la_vache", hidden=True)
def la_vache():
    """Fetchez La Vache."""

    click.echo("🐄")
    # import time
    # import shutil

    # loops = 1
    # screen_width, _ = shutil.get_terminal_size()

    # for _ in range(loops):
    #     for spaces in range(screen_width - 1):
    #         click.echo(f"\r{' ' * spaces}🐄", nl=False)
    #         time.sleep(0.025)

    #     for spaces in range(screen_width - 1, -1, -1):
    #         click.echo(f"\r{' ' * spaces"}🐄, nl=False)
    #         time.sleep(0.025)


cli.add_command(la_vache, name="lavache")
cli.add_command(pipeline_group, name="run")
cli.add_command(modules_group, name="modules")
cli.add_command(hooks_group, name="hooks")
cli.add_command(recipes_group, name="recipes")
cli.add_command(streams_group, name="streams")
cli.add_command(data_types_group, name="datatypes")
cli.add_command(regions_group, name="regions")
cli.add_command(cache_group, name="cache")


if __name__ == "__main__":
    cli()
