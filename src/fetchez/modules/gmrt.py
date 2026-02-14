#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.gmrt
~~~~~~~~~~~~~

Fetch data from the Global Multi-Resolution Topography (GMRT) synthesis.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from typing import Optional
from fetchez import core
from fetchez import utils
from fetchez import spatial
from fetchez import cli

logger = logging.getLogger(__name__)

GMRT_URL = "https://www.gmrt.org"
GMRT_POINT_URL = "https://www.gmrt.org:443/services/PointServer?"
GMRT_GRID_URL = "https://www.gmrt.org:443/services/GridServer?"
GMRT_GRID_URLS_URL = "https://www.gmrt.org:443/services/GridServer/urls?"
GMRT_METADATA_URL = "https://www.gmrt.org/services/GridServer/metadata?"
GMRT_SWATH_URL = "https://www.gmrt.org/shapefiles/gmrt_swath_polygons.zip"

# GMRT seems to require specific user agents (Firefox/Windows)
GMRT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
    )
}


# =============================================================================
## GMRT Functions
# =============================================================================
def gmrt_fetch_point(latitude: float, longitude: float) -> Optional[str]:
    """Fetch a single point elevation from GMRT."""

    data = {"longitude": longitude, "latitude": latitude}

    req = core.Fetch(GMRT_POINT_URL, headers=GMRT_HEADERS).fetch_req(
        params=data, tries=10, timeout=2
    )

    if req is not None:
        return req.text
    return None


@cli.cli_opts(
    help_text="Global Multi-Resolution Topography (GMRT) Synthesis",
    res="Resolution to fetch (default, max, or specific value)",
    fmt="Output format (geotiff, netcdf, etc.)",
    layer="Data layer (topo, topo-mask)",
    want_swath="Fetch swath polygon shapefile instead of grid",
)
class GMRT(core.FetchModule):
    """The Global Multi-Resolution Topography synthesis.

    The Global Multi-Resolution Topography (GMRT) synthesis is a multi-resolutional
    compilation of edited multibeam sonar data collected by scientists and
    institutions worldwide, that is reviewed, processed and gridded by the GMRT
    Team and merged into a single continuously updated compilation of global elevation
    data.

    Data Formats:
      - GMT v3 Compatible NetCDF (GMT id=cf)
      - COARDS/CF1.6 Compliant NetCDF (GMT id=nd)
      - ESRI ArcASCII
      - GeoTIFF

    Layers: 'topo' or 'topo-mask'

    Data is assumed instantaneous MSL.
    """

    def __init__(
        self,
        res: str = "default",
        fmt: str = "geotiff",
        layer: str = "topo",
        want_swath: bool = False,
        **kwargs,
    ):
        super().__init__(name="gmrt", **kwargs)

        self.res = res
        self.fmt = fmt
        self.want_swath = want_swath

        # Validate layer
        self.layer = layer if layer in ["topo", "topo-mask"] else "topo"

        # Buffer the input region and correct to wgs extremes
        # GMRT specific: 2.33% buffer, 0.0088 increment
        if self.region is not None:
            self.gmrt_region = spatial.buffer_region(self.region, p=2.33)
            # todo: implement/port wgs_extremes (from cudem.regions)
            # self.gmrt_region._wgs_extremes(just_below=True)
        else:
            self.gmrt_region = None

        # Metadata for DLIM/Processing
        self.data_format = 200
        self.src_srs = "epsg:4326+3855"
        self.title = "GMRT"
        self.source = "GMRT"
        self.date = None
        self.data_type = "Raster"
        self.resolution = None
        self.hdatum = "wgs84"
        self.vdatum = "msl"
        self.url = GMRT_URL
        self.headers = GMRT_HEADERS

    def run(self):
        """Run the GMRT fetching module."""

        if self.region is None or self.gmrt_region is None:
            return []

        w, e, s, n = self.gmrt_region

        self.data = {
            "north": n,
            "west": w,
            "south": s,
            "east": e,
            "mformat": "json",
            "resolution": self.res,
            "format": self.fmt,
            "layer": self.layer,
        }

        req = core.Fetch(GMRT_GRID_URL, headers=self.headers).fetch_req(
            params=self.data, tries=10, timeout=2
        )

        if req is not None:
            ext = "tif" if self.fmt == "geotiff" else "grd"

            # Construct filename
            r_str = f"w{w:.2f}_s{s:.2f}"
            outf = f"gmrt_{self.layer}_{self.res}_{r_str}.{ext}"

            # Populate `self.results`
            # add some useful info at the end...
            self.add_entry_to_results(
                url=req.url,
                dst_fn=outf,
                data_type="gmrt",
                srs=self.src_srs,  # epsg:4326+3855
                bounds=self.gmrt_region,  # (w, e, s, n)
                resolution=self.res,  # e.g., 'max' or '30m'
                date=utils.this_date(),  # e.g., '2025' (GMRT is a synthesis)
                remote_size=req.headers.get(
                    "Content-Length"
                ),  # Useful for progress bars
                layer=self.layer,  # 'topo' vs 'topo-mask'
            )

        return self
