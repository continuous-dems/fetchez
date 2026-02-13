#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.osm
~~~~~~~~~~~~~~~~~~~

Fetch OpenStreetMap (OSM) data via the Overpass API.

:copyright: (c) 2020 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

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

    **Raw Queries:**
      You can pass raw Overpass QL. Use `{bbox}` as a placeholder for
      the bounding box (e.g., `node["amenity"="pub"]({bbox}); out;`).
    """

    def __init__(self, query: str = "coastline", chunk_size: str = None, **kwargs):
        super().__init__(name="osm", **kwargs)
        self.query_type = query
        self.chunk_size = float(chunk_size) if chunk_size else None

        if query in PRESETS:
            self.ql_template = PRESETS[query]
            self.file_tag = query
        else:
            self.ql_template = query
            self.file_tag = "custom"

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
            w, e, s, n = chunk

            ql = self._build_query(chunk)

            # swithc to POST?
            params = {"data": ql}
            full_url = f"{OVERPASS_API}?{urlencode(params)}"

            r_str = f"w{w:.2f}_e{e:.2f}_s{s:.2f}_n{n:.2f}".replace(".", "p").replace(
                "-", "m"
            )
            out_fn = f"osm_{self.file_tag}_{r_str}.osm"

            self.add_entry_to_results(
                url=full_url,
                dst_fn=out_fn,
                data_type="osm_xml",
                agency="OpenStreetMap",
                title=f"OSM {self.file_tag.title()} (Chunk {i + 1})",
            )

        return self
