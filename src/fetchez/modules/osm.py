#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.osm
~~~~~~~~~~~~~~~~~~~

Fetch OpenStreetMap (OSM) data via the Overpass API.

:copyright: (c) 2020 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from typing import Optional
from urllib.parse import urlencode
from fetchez import core
from fetchez import cli
from fetchez import spatial

OVERPASS_API = "https://overpass-api.de/api/interpreter"

# Pre-defined queries for common use cases
PRESETS = {
    "coastline": """
        (
          way["natural"="coastline"]({bbox});
          relation["natural"="coastline"]({bbox});
        );
        (._;>;);
        out meta;
    """,
    "water": """
        (
          way["natural"="water"]({bbox});
          relation["natural"="water"]({bbox});
        );
        (._;>;);
        out meta;
    """,
    "buildings": """
        (
          way["building"]({bbox});
          relation["building"]({bbox});
        );
        (._;>;);
        out meta;
    """,
    "highways": """
        (
          way["highway"]({bbox});
        );
        (._;>;);
        out meta;
    """,
}


# =============================================================================
# OSM Module
# =============================================================================
@cli.cli_opts(
    help_text="OpenStreetMap (via Overpass API)",
    query="Preset ('coastline', 'water', 'buildings') or raw Overpass QL.",
    tag="Dynamic Tag Search (e.g. 'amenity=pub' or 'leisure=park'). Overrides query.",
    chunk_size="Split region into chunks of N degrees (e.g. 0.5) to avoid timeouts.",
)
class OSM(core.FetchModule):
    """Fetch raw OpenStreetMap data using the Overpass API.

    This module handles the complexity of querying Overpass, including
    automatic bounding box formatting and region chunking (to avoid
    server timeouts on large areas).

    **Presets:**
      - coastline: 'natural=coastline' (High-res shorelines)
      - water: 'natural=water' (Lakes, ponds)
      - buildings: 'building=*' (Footprints)
      - highways: 'highway=*' (Roads)

    **Modes:**
      1. Preset: --query coastline
      2. Dynamic Tag: --tag amenity=hospital
      3. Raw QL: --query "node['name'='Paris']; out;"

    **Raw Queries:**
      You can pass raw Overpass QL. Use `{bbox}` as a placeholder for
      the bounding box (e.g., `node["amenity"="pub"]({bbox}); out;`).
    """

    def __init__(
        self,
        query: str = "coastline",
        tag: Optional[str] = None,
        chunk_size: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(name="osm", **kwargs)
        self.query_type = query
        self.chunk_size = float(chunk_size) if chunk_size else None

        if tag:
            self.ql_template = self._build_tag_template(tag)
            self.file_tag = tag.replace("=", "_").replace(":", "")
        # Priority 2: Preset
        elif query in PRESETS:
            self.ql_template = PRESETS[query]
            self.file_tag = query
        # Priority 3: Raw QL
        else:
            self.ql_template = query
            self.file_tag = "custom"

    def _build_tag_template(self, tag_str):
        """Construct QL for a specific tag (key=value or key)."""

        if "=" in tag_str:
            k, v = tag_str.split("=", 1)
            selector = f'["{k}"="{v}"]'
        else:
            selector = f'["{tag_str}"]'

        # Search Nodes, Ways, and Relations for this tag
        return f"""(
          node{selector}({{bbox}});
          way{selector}({{bbox}});
          relation{selector}({{bbox}});
        );
        (._;>;);
        out meta;"""

    def _build_query(self, region):
        """Inject bbox into the QL template."""

        w, e, s, n = region
        bbox_str = f"{s},{w},{n},{e}"
        header = "[timeout:180][maxsize:1073741824];"
        body = self.ql_template.replace("{bbox}", bbox_str)
        return f"{header}{body}"

    def run(self):
        """Run the OSM fetch"""

        if self.region is None:
            return []

        if self.chunk_size:
            chunks = spatial.chunk_region(self.region, self.chunk_size)
        else:
            chunks = [self.region]

        for i, chunk in enumerate(chunks):
            ql = self._build_query(chunk)
            params = {"data": ql}
            full_url = f"{OVERPASS_API}?{urlencode(params)}"

            w, e, s, n = chunk
            # r_str = f"w{w:.2f}_n{n:.2f}".replace(".", "p").replace("-", "m")
            r_str = f"w{w:.2f}_e{e:.2f}_s{s:.2f}_n{n:.2f}".replace(".", "p").replace(
                "-", "m"
            )
            out_fn = f"osm_{self.file_tag}_{r_str}.osm"

            self.add_entry_to_results(
                url=full_url,
                dst_fn=out_fn,
                data_type="osm_xml",
                agency="OpenStreetMap",
                title=f"OSM {self.file_tag} (Chunk {i + 1})",
            )

        return self
