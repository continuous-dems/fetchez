#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli.data_types
~~~~~~~~~~~~~~~~

Discoverability and documentation for fetchez data_type Detectors.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click

from fetchez.registry import DetectorRegistry
from fetchez.utils import (
    get_class_arguments,
    group_registry_by_key,
    print_grouped_registry,
    FetchezMainGroup,
    FetchezMainCommand,
)
from fetchez.api import search_detectors


@click.group(
    cls=FetchezMainGroup,
    name="detectors",
    fetchez_commands=["list", "info", "detect"],
)
def detectors_group():
    """Discover, search, and learn about data type detectors.

    \b
    Detectors of the the underlying Python classes (like `extension` or
    `signature`) that detect the Fetchez data_type of a geospatial file.

    \b
    Usage:
      You rarely call Detectors directly. They are automatically triggered by the
      `stream-init` hook based on the geospatial data file being processed.

    \b
      Datatype Detectors can be initiated with the `stream-init` hook which
      will populate entry['data_type'] in the pipeline.
    """

    pass


@detectors_group.command("list", cls=FetchezMainCommand)
@click.option("--search", "-s", help="Filter detectors by name or keyword.")
def detectors_list(search):
    """List all available detectors grouped by category."""

    registry = search_detectors(search)
    grouped_hooks = group_registry_by_key(registry, "mod")
    print_grouped_registry(grouped_hooks, "Category")
    click.echo(
        "\nRun 'fetchez detectors info <name>' for arguments and recipe examples.\n"
    )


@detectors_group.command("info", cls=FetchezMainCommand)
@click.argument("name")
def detectors_info(name):
    """Show arguments and examples for a specific detector."""

    DetectorRegistry.load_all()
    schema_cls = DetectorRegistry.get_class(name)
    meta = DetectorRegistry.get_info(name)

    if not schema_cls:
        click.secho(f"Error: Detector '{name}' not found.", fg="red")
        sys.exit(1)

    click.secho(f"\n🌐 DETECTOR: {name}", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"  Description : {meta.get('desc', 'N/A')}")
    click.echo(f"  Category    : {meta.get('category', 'N/A')}\n")
    click.echo(f"  Priority    : {meta.get('priority', 'N/A')}\n")

    # print_class_arguments(schema_cls)
    args_dict = get_class_arguments(schema_cls)
    if args_dict:
        click.secho("  Arguments:", fg="yellow", bold=True)
        for key, val in args_dict.items():
            click.echo(f"    - {click.style(key, bold=True)} {val['default']}")

    click.echo("\n" + "-" * 40 + "\n")


@detectors_group.command("detect", cls=FetchezMainCommand)
@click.argument("name")
def detectors_detect(name):
    """Detect a Fetchez data_type from a filename or Fetchez entry."""

    from fetchez.datatypes.detectors import detect_entry

    entry = {"url": None, "dst_fn": name}
    click.echo(detect_entry(entry))
