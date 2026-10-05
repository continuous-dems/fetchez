#!/usr/bin/env python

"""
fetchez.modules.path
~~~~~~~~~~~~~~~~~~~~

Generic module to treat local files like remote ones.
Useful for injecting local data into the processing pipeline (dlim).

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path

from fetchez import cli
from fetchez.modules import FetchModule


@cli.cli_opts(
    help_text="Process local files (e.g. for piping/hooks)",
    paths="List of input file paths",
    path="Single input file path (legacy)",
)
class LocalDataset(FetchModule):
    name = "file"
    meta_category = "Local Data"
    meta_desc = "Explicitly pass specific local files (No spatial filtering)"
    meta_agency = "Local"
    meta_resolution = "N/A"
    meta_tags = ["local", "file"]
    meta_region = "Global"
    meta_license = "MIT (Fetchez Core)"
    meta_urls: dict[str, str] = {}

    """Register local files into the fetchez pipeline."""

    def __init__(self, paths=None, path=None, **kwargs):
        """
        Args:
            paths (list): A list of file paths.
            path (str): A single file path (optional) (can be sep by commas).
        """

        super().__init__(**kwargs)

        # Normalize inputs into a single list
        self.file_list = []

        if paths:
            if isinstance(paths, list):
                self.file_list.extend(paths)
            else:
                for this_path in paths.split(","):
                    if Path(this_path).is_file():
                        self.file_list.append(this_path)

        if path:
            for this_path in path.split(","):
                if Path(this_path).is_file():
                    self.file_list.append(this_path)

        # Register each file
        for p in self.file_list:
            self._add_file_entry(p)

    def _add_file_entry(self, p):
        """Helper to format and register a single file."""

        if not p:
            return

        # Handle file:// schema if present
        if p.startswith("file://"):
            clean_path = p.replace("file://", "")
            abs_path = Path(clean_path).resolve()
            url = f"file://{abs_path}"
        else:
            abs_path = Path(p).resolve()
            url = f"file://{abs_path}"

        # Determine a "destination filename" (just the basename)
        # This is what hooks will see as 'dst_fn'
        # filename = os.path.basename(abs_path)

        # We set status=0 so Fetchez Core thinks it's "Already Downloaded"
        # and proceeds immediately to the hooks.
        self.add_entry_to_results(
            url=url,
            dst_fn=str(abs_path),  # Point directly to the absolute local path
            data_type="local",
            status=0,
        )

    def run(self):
        pass
