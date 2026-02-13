#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
generate_module_table.py
~~~~~~~~~~~~~~~~~~~~~~~~

Generates a Markdown (or HTML) table of all available Fetchez modules
using the FetchezRegistry.

Usage:
    python generate_module_table.py > MODULES.md
    python generate_module_table.py --html > modules.html
"""

import sys
import argparse
from fetchez.registry import FetchezRegistry

def generate_markdown_table(modules):
    """Generate a standard Markdown table."""

    # Header
    md = []
    md.append("| Module | Category | Description | Agency | Region | License |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    for key in sorted(modules.keys()):
        meta = FetchezRegistry.get_info(key)

        if meta.get('category') == 'Generic' and key not in ['earthdata', 'http']:
            continue

        name = f"**`{key}`**"
        home_url = meta.get('urls', {}).get('home')
        if home_url:
            agency = f"[{meta.get('agency', 'Unknown')}]({home_url})"
        else:
            agency = meta.get('agency', '-')

        desc = meta.get('desc', '-')
        cat = meta.get('category', '-')
        region = meta.get('region', 'Global')
        license = meta.get('license', '-')

        desc = desc.replace('|', '/')
        license = license.replace('|', '/')

        row = f"| {name} | {cat} | {desc} | {agency} | {region} | {license} |"
        md.append(row)

    return "\n".join(md)


def generate_html_table(modules, fragment=True):
    """Generate an HTML table with DataTables (sortable/searchable)."""

    rows = []
    for key in sorted(modules.keys()):
        meta = FetchezRegistry.get_info(key)

        home_url = meta.get('urls', {}).get('home', '#')

        rows.append(f"""
        <tr>
            <td><code>{key}</code></td>
            <td>{meta.get('category', '-')}</td>
            <td>{meta.get('desc', '-')}</td>
            <td><a href="{home_url}" target="_blank">{meta.get('agency', '-')}</a></td>
            <td>{meta.get('region', '-')}</td>
            <td>{meta.get('resolution', '-')}</td>
            <td>{meta.get('license', '-')}</td>
        </tr>
        """)

    if fragment:
        html = f"""
        <link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">

        <style>
            /* Overrides to make it fit Sphinx themes better */
            table.dataTable {{ font-size: 0.9em; }}
            .dataTables_wrapper {{ margin-top: 20px; }}
            code {{ background: #e3e3e3; padding: 2px 4px; border-radius: 3px; color: #333; }}
        </style>

        <div style="overflow-x: auto;">
            <table id="moduleTable" class="display" style="width:100%">
                <thead>
                    <tr>
                        <th>Module</th>
                        <th>Category</th>
                        <th>Description</th>
                        <th>Agency</th>
                        <th>Region</th>
                        <th>Resolution</th>
                        <th>License</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>

        <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>

        <script>
            $(document).ready(function () {{
                $('#moduleTable').DataTable({{
                    "pageLength": 25,
                    "lengthMenu": [[10, 25, 50, -1], [10, 25, 50, "All"]],
                    "order": [[ 0, "asc" ]]
                }});
            }});
        </script>
        """
    else:
        html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fetchez Module Catalog</title>
        <link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">
        <style>
            body {{ font-family: sans-serif; padding: 20px; }}
            code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-weight: bold; }}
            a {{ text-decoration: none; color: #0366d6; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>Fetchez Data Catalog</h1>
        <p>Current version includes {len(modules)} data modules.</p>

        <table id="moduleTable" class="display" style="width:100%">
            <thead>
                <tr>
                    <th>Module</th>
                    <th>Category</th>
                    <th>Description</th>
                    <th>Agency</th>
                    <th>Region</th>
                    <th>Resolution</th>
                    <th>License</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>

        <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready(function () {{
                $('#moduleTable').DataTable({{
                    "pageLength": 25,
                    "order": [[ 1, "asc" ]] // Sort by Category default
                }});
            }});
        </script>
    </body>
    </html>
        """

    return html

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", action="store_true", help="Output interactive HTML instead of Markdown")
    parser.add_argument("--html-fragment", action="store_true", help="Output interactive HTML fragment instead of full page")
    args = parser.parse_args()

    all_modules = FetchezRegistry._modules

    if args.html or args.html_fragment:
        print(generate_html_table(all_modules, fragment=args.html_fragment))
    else:
        print(generate_markdown_table(all_modules))
