#!/usr/bin/env python

"""
fetchez.cli.cache
~~~~~~~~~~~~~~~~

Manage fetchez caches.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import shutil
import time
from pathlib import Path

import click

from fetchez.utils import FetchezMainCommand, FetchezMainGroup

CACHE_COMMANDS = ["info", "clear", "update-registry"]


@click.group(
    cls=FetchezMainGroup,
    name="cache",
    fetchez_commands=CACHE_COMMANDS,
)
def cache_group():
    """Manage the hidden Fetchez cache."""


@cache_group.command("info", cls=FetchezMainCommand)
@click.option("-D", "--dir", required=True, help="Target directory to inspect.")
def cache_info(dir):
    """Display information about local cache usage."""

    from math import floor

    # TODO: Add lock option to info and remove .lock files.
    # lock = True
    # if lock:
    #     files = list(Path(dir).glob("**/*.lock"))
    #     cache_parents = {Path(*f.parts[: -1]) for f in files}
    # else:
    files = list(Path(dir).glob("**/.fetchez_cache/**/*.json"))
    cache_parents = {Path(*f.parts[: f.parts.index(".fetchez_cache")]) for f in files}

    if not files:
        click.secho("No cache found in this directory.", fg="yellow")
        return

    cache_ages = [floor((time.time() - os.path.getmtime(f)) / 86400) for f in files]
    total_age = (
        f"{min(cache_ages)} - {max(cache_ages)}"
        if (min(cache_ages) < max(cache_ages))
        else f"{max(cache_ages)}"
    )

    # This is just the size of the .json files, we should update this or add
    # an option to get the filesize of the referenced data.
    total_size = sum(f.stat().st_size for f in files) / (1024 * 1024)

    for cache_parent in cache_parents:
        click.secho(f"Cache Directory : {cache_parent.resolve()}", fg="cyan", bold=True)

    click.echo(f"{'-' * 60}")
    click.echo(f"Files Cached    : {len(files)}")
    click.echo(f"Total Size      : {total_size:.2f} MB")
    click.echo(f"Cache Age       : {total_age} Days")


@cache_group.command("clear", cls=FetchezMainCommand)
@click.option(
    "-D", "--dir", default=".", required=True, help="Target directory to clear."
)
def cache_clear(dir):
    """Safely delete the local Fetchez cache."""

    cache_dirs = list(Path(dir).glob("**/.fetchez_cache"))
    # print(cache_dirs)
    # cache_path = Path(dir) / ".fetchez_cache"
    for cache_path in cache_dirs:
        if cache_path.exists():
            shutil.rmtree(cache_path)
            click.secho(
                f"✨ Cache cleared successfully from {cache_path}!",
                fg="green",
                bold=True,
            )
        else:
            click.echo("No cache to clear.")
