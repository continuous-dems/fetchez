#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.etopo
~~~~~~~~~~~~~~~~~~~~~~

Fetch ETOPO 2022 Global Relief Model data from NOAA NCEI.

ETOPO 2022 is available in:
1.  **15 arc-second tiles:** (Approx 450m) Tiled in 15x15 degree chunks.
2.  **30 & 60 arc-second:** (Approx 900m & 1800m) Global single files.

Note on 'Bed' vs 'Surface':
In ETOPO 2022, 'Bed' elevation (under ice) is only provided as distinct files
over Greenland and Antarctica. For the rest of the world, 'Bed' is identical
to 'Surface'. This module automatically falls back to 'Surface' if 'Bed'
is requested but not found for a specific tile.

:copyright: (c) 2022 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

from fetchez import core
from fetchez import fred
from fetchez import cli

logger = logging.getLogger(__name__)

ETOPO_BASE_URL_15S_GTIF = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/"
)
ETOPO_BASE_URL_15S_NC = (
    "https://www.ngdc.noaa.gov/thredds/fileServer/global/ETOPO2022/15s/"
)
ETOPO_BASE_URL_30S_GTIF = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/30s/"
)
ETOPO_BASE_URL_60S_GTIF = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/"
)

ETOPO_URLS = {
    "15s": {
        "bed": f"{ETOPO_BASE_URL_15S_GTIF}15s_bed_elev_gtif/",
        "bed_sid": f"{ETOPO_BASE_URL_15S_GTIF}15s_bed_sid_gtif/",
        "surface": f"{ETOPO_BASE_URL_15S_GTIF}15s_surface_elev_gtif/",
        "surface_sid": f"{ETOPO_BASE_URL_15S_GTIF}15s_surface_sid_gtif/",
    },
    "30s": {
        "bed": f"{ETOPO_BASE_URL_30S_GTIF}30s_bed_elev_gtif/ETOPO_2022_v1_30s_N90W180_bed.tif",
        "surface": f"{ETOPO_BASE_URL_30S_GTIF}30s_surface_elev_gtif/ETOPO_2022_v1_30s_N90W180_surface.tif",
    },
    "60s": {
        "bed": f"{ETOPO_BASE_URL_60S_GTIF}60s_bed_elev_gtif/ETOPO_2022_v1_60s_N90W180_bed.tif",
        "surface": f"{ETOPO_BASE_URL_60S_GTIF}60s_surface_elev_gtif/ETOPO_2022_v1_60s_N90W180_surface.tif",
    },
}

NETCDF_BASE_URLS = {
    "bed": f"{ETOPO_BASE_URL_15S_NC}15s_bed_elev_netcdf/",
    "bed_sid": f"{ETOPO_BASE_URL_15S_NC}15s_bed_sid_netcdf/",
    "surface": f"{ETOPO_BASE_URL_15S_NC}15s_surface_elev_netcdf/",
    "surface_sid": f"{ETOPO_BASE_URL_15S_NC}15s_surface_sid_netcdf/",
}


# =============================================================================
# ETOPO Module
# =============================================================================
@cli.cli_opts(
    help_text="ETOPO 2022 Global Relief Model",
    resolution="Resolution: '15s' (Tiled), '30s' (Global), '60s' (Global). Default: 15s",
    datatype="Data Type: 'bed', 'surface', 'bed_sid', 'surface_sid'. Default: bed",
    format="File Format: 'gtif' or 'netcdf'. Default: gtif",
    update="Force update of the local index (FRED)",
)
class ETOPO(core.FetchModule):
    """Fetch ETOPO 2022 data.

    Automatically handles fallback from 'bed' to 'surface' for non-ice regions.
    """

    def __init__(
        self,
        resolution: str = "15s",
        datatype: str = "bed",
        format: str = "gtif",
        update: bool = False,
        **kwargs,
    ):
        super().__init__(name="etopo", **kwargs)
        self.resolution = resolution if resolution in ETOPO_URLS else "15s"
        self.datatype = datatype
        self.file_format = format
        self.force_update = update

        if self.resolution == "15s":
            self.fred = fred.FRED(name="etopo")
            if self.force_update or len(self.fred.features) == 0:
                self.update_index()

    def update_index(self):
        """Crawl the ETOPO 15s directories and update the FRED index."""

        logger.info("Updating ETOPO 15s Index from NOAA...")

        self.fred.features = []
        count = 0

        for dtype, url in ETOPO_URLS["15s"].items():
            page = core.Fetch(url).fetch_html()
            if page is None:
                continue

            rows = page.xpath('//a[contains(@href, ".tif")]/@href')

            for row in rows:
                filename = row.split("/")[-1]
                sid = filename.split(".")[0]

                try:
                    # Parse spatial info from filename (e.g. N90W180)
                    parts = sid.split("_")
                    spat = next(
                        (
                            p
                            for p in parts
                            if ("N" in p or "S" in p) and ("E" in p or "W" in p)
                        ),
                        None,
                    )
                    if not spat:
                        continue

                    xsplit = "E" if "E" in spat else "W"
                    ysplit = "S" if "S" in spat else "N"

                    parts_geo = spat.split(xsplit)
                    y = int(parts_geo[0].split(ysplit)[-1])
                    x = int(parts_geo[-1])

                    if xsplit == "W":
                        x = -x
                    if ysplit == "S":
                        y = -y

                    w, e = float(x), float(x + 15)
                    n, s = float(y), float(y - 15)

                    geom = {
                        "type": "Polygon",
                        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
                    }

                    self.fred.add_survey(
                        geom=geom,
                        Name=sid,
                        ID=sid,
                        Agency="NOAA",
                        DataLink=f"{url}{row}",
                        DataType=dtype,
                        DataFormat="gtif",
                        Date="2022",
                        Info="ETOPO 2022 (15s GeoTIFF)",
                    )

                    nc_base = NETCDF_BASE_URLS.get(dtype)
                    if nc_base:
                        self.fred.add_survey(
                            geom=geom,
                            Name=f"{sid}_nc",
                            ID=sid,
                            Agency="NOAA",
                            DataLink=f"{nc_base}{sid}.nc",
                            DataType=dtype,
                            DataFormat="netcdf",
                            Date="2022",
                            Info="ETOPO 2022 (15s NetCDF)",
                        )
                    count += 1
                except Exception:
                    continue

        logger.info(f"Indexed {count} ETOPO 15s datasets.")
        self.fred.save()

    def run(self):
        """Run the ETOPO fetching module."""

        # --- Global Files ---
        if self.resolution in ["30s", "60s"]:
            url = ETOPO_URLS[self.resolution].get(self.datatype)
            if url:
                self.add_entry_to_results(
                    url=url,
                    dst_fn=f"ETOPO_2022_{self.resolution}_{self.datatype}.tif",
                    data_type="etopo_gtif",
                    agency="NOAA",
                    title=f"ETOPO 2022 Global ({self.resolution})",
                    license="Public Domain",
                )
            return self

        # --- Tiled Files (15s) with Smart Fallback ---
        if self.region is None:
            return []

        results = self.fred.search(
            region=self.region,
            where=[
                f"DataType = '{self.datatype}'",
                f"DataFormat = '{self.file_format}'",
            ],
        )

        # 'bed' == 'surface' where no ice exists
        if not results and "bed" in self.datatype:
            fallback_type = self.datatype.replace("bed", "surface")
            logger.info(
                f"No '{self.datatype}' tiles found. Falling back to '{fallback_type}' (identical for non-ice regions)."
            )

            results = self.fred.search(
                region=self.region,
                where=[
                    f"DataType = '{fallback_type}'",
                    f"DataFormat = '{self.file_format}'",
                ],
            )

        for item in results:
            self.add_entry_to_results(
                url=item["DataLink"],
                dst_fn=item["DataLink"].split("/")[-1],
                data_type=f"etopo_{self.file_format}",
                agency="NOAA",
                title=item["Name"],
                license="Public Domain",
            )

        return self
