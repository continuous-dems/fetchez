"""
module_table
~~~~~~~~~~~~~

Sphinx extension that generates an interactive HTML table of Fetchez modules
using the FetchezRegistry.

Usage in RST::

    .. module-table::

Usage in MyST Markdown::

    ```{module-table}
    ```
"""

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from fetchez.registry import FetchezRegistry


class ModuleTableDirective(SphinxDirective):
    """Directive to generate an interactive module table using DataTables."""

    has_content = False
    required_arguments = 0
    optional_arguments = 0

    def run(self):
        modules = FetchezRegistry._modules

        rows = []
        for key in sorted(modules.keys()):
            meta = FetchezRegistry.get_info(key)

            if meta.get("category") == "Generic" and key not in ["earthdata", "https"]:
                continue

            home_url = meta.get("urls", {}).get("home", "#")

            rows.append(f"""
            <tr>
                <td><code>{key}</code></td>
                <td>{meta.get("category", "-")}</td>
                <td>{meta.get("desc", "-")}</td>
                <td><a href="{home_url}" target="_blank">{meta.get("agency", "-")}</a></td>
                <td>{meta.get("region", "-")}</td>
                <td>{meta.get("resolution", "-")}</td>
                <td>{meta.get("license", "-")}</td>
            </tr>
            """)

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

        raw_node = nodes.raw("", html, format="html")
        return [raw_node]


def setup(app: Sphinx):
    """Register the extension with Sphinx."""
    app.add_directive("module-table", ModuleTableDirective)

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
