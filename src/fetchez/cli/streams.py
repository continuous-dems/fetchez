#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.streams
~~~~~~~~~~~~~~~~

Discoverability and documentation for processing readers.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click

from fetchez.api import search_streams
from fetchez.cli.utils import (
    filter_registry,
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from .readers import readers_group
from .profiles import profiles_group

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

    pass


@streams_group.command("list", cls=FetchezMainCommand)
@click.option(
    "--group-by",
    type=click.Choice(["provider", "category", "stage", "effects"]),
    default="provider",
    help="Group results by type.",
)
@click.option("--search", help="Filter results by search term.")
@click.option(
    "--provider",
    multiple=True,
    help="Filter by provider (repeat to include multiple providers).",
)
def stream_list(group_by, search, provider):
    """List all available streams grouped by provider and category."""

    registry = search_streams(search)

    registry = filter_registry(
        registry,
        {
            "provider": provider,
        },
    )

    group_key = "provider" if group_by == "provider" else group_by

    grouped_streams = group_registry_by_key(registry, group_key)
    print_grouped_registry(grouped_streams, "Streams", group_by.title())
    click.echo(
        "\nRun 'fetchez streams info <name>' for arguments and recipe examples.\n"
    )


streams_group.add_command(readers_group, name="readers")
streams_group.add_command(profiles_group, name="profiles")
