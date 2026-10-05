#!/usr/bin/env python

"""
fetchez.cli.streams
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing readers.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click

from fetchez.api import search_streams
from fetchez.utils import (
    FetchezMainCommand,
    FetchezMainGroup,
    group_registry_by_key,
    print_grouped_registry,
)

from .profiles import profiles_group
from .readers import readers_group

STREAMS_COMMANDS = ["readers", "profiles"]


@click.group(cls=FetchezMainGroup, name="streams", fetchez_commands=STREAMS_COMMANDS)
def streams_group():
    """Discover, search, and learn about streams.

    \b
    When Fetchez downloads a file (like a GeoTIFF or NetCDF), it can use Streams
    to read the data piece-by-piece in memory. This allows for  control over how
    to process different datasets.

    \b
    This command group lets you explore the internal 'Readers' that parse the
    files, and the 'Profiles' that tell those readers exactly how to behave.
    """


@streams_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter streamss by name or keyword.")
def stream_list(search):
    """List all available streams grouped by provider and category."""

    registry = search_streams(search)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Streams", "Provider")
    click.echo(
        "\nRun 'fetchez streams info <name>' for arguments and recipe examples.\n"
    )


streams_group.add_command(readers_group, name="readers")
streams_group.add_command(profiles_group, name="profiles")
