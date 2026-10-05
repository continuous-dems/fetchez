#!/usr/bin/env python

"""
fetchez.modules.gmrt
~~~~~~~~~~~~~~~~~~~~

Fetch data from the Global Multi-Resolution Topography (GMRT) synthesis.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez import cli, core, spatial, utils
from fetchez.modules import FetchModule

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
def gmrt_fetch_point(latitude: float, longitude: float) -> str | None:
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
class GMRT(FetchModule):
    name = "gmrt"
    meta_category = "Bathymetry"
    meta_desc = "Global Multi-Resolution Topography Synthesis"
    meta_agency = "Lamont-Doherty Earth Observatory"
    meta_tags = ["bathymetry", "ocean", "global", "synthesis", "grid"]
    meta_region = "Global"
    meta_resolution = "Varies (100m - 400m)"
    meta_license = "CC-BY-4.0"
    meta_urls = {
        "home": "https://www.gmrt.org",
        "citation": "https://www.gmrt.org/about/citation.php",
    }

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
        if self.wgs_region is not None:
            self.gmrt_region = spatial.buffer_region(self.wgs_region, p=2.33)
            # todo: implement/port wgs_extremes (from cudem.regions)
            # self.gmrt_region._wgs_extremes(just_below=True)
        else:
            self.gmrt_region = None

        self.headers = GMRT_HEADERS

    def run(self):
        """Run the GMRT fetching module. Prefers pre-rendered tiles for stability."""

        if self.wgs_region is None or self.gmrt_region is None:
            return []

        w, e, s, n = self.gmrt_region
        ext = "tif" if self.fmt == "geotiff" else "grd"

        self.data = {
            "north": n,
            "west": w,
            "south": s,
            "east": e,
            "mformat": "json",
            "resolution": self.res,
            "format": self.fmt,
            # "layer": self.layer,
        }

        try:
            req_urls = core.Fetch(GMRT_GRID_URLS_URL, headers=self.headers).fetch_req(
                params=self.data, tries=5, timeout=10
            )

            if req_urls and req_urls.status_code == 200:
                logger.debug(f"GMRT url: {req_urls.url}")
                urls = req_urls.json()

                if urls and isinstance(urls, list):
                    logger.debug(
                        f"[GMRT] Found {len(urls)} pre-rendered static tiles for region."
                    )
                    for url in urls:
                        import os
                        import urllib.parse

                        parsed = urllib.parse.urlparse(url)
                        dst_fn = os.path.basename(parsed.path)

                        if not dst_fn or not dst_fn.endswith(f".{ext}"):
                            dst_fn = f"gmrt_{self.layer}_{self.res}_{hash(url)}.{ext}"

                        self.add_entry_to_results(
                            url=url,
                            dst_fn=dst_fn,
                            data_type="gmrt",
                            srs="epsg:4326",
                            bounds=self.gmrt_region,
                            resolution=self.res,
                            date=utils.this_date(),
                            layer=self.layer,
                        )

                    if self.results:
                        return self

        except Exception as e:
            logger.exception(
                f"[GMRT] Failed to fetch static tile URLs: {e}. Falling back to dynamic gridder..."
            )

        req = core.Fetch(GMRT_GRID_URL, headers=self.headers).fetch_req(
            params=self.data, tries=10, timeout=15
        )

        if req is not None and req.status_code == 200:
            r_str = f"w{w:.2f}_s{s:.2f}"
            outf = f"gmrt_{self.layer}_{self.res}_{r_str}.{ext}"

            self.add_entry_to_results(
                url=req.url,
                dst_fn=outf,
                data_type="gmrt",
                srs="epsg:4326",
                bounds=self.gmrt_region,
                resolution=self.res,
                date=utils.this_date(),
                remote_size=req.headers.get("Content-Length"),
                layer=self.layer,
            )

        return self
