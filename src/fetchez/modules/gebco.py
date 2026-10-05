#!/usr/bin/env python

"""
fetchez.modules.gebco
~~~~~~~~~~~~~~~~~~~~~

Fetch General Bathymetric Chart of the Oceans (GEBCO) data.
Supports regional subsetting via Cloud Optimized GeoTIFF (COG)
or full global downloads from BODC.
"""

import logging
import math
import urllib.parse

from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


class GEBCO_Base(FetchModule):
    """Base class to dynamically construct GEBCO THREDDS URLs based on year."""

    # name = "gebco"
    meta_category = "Bathymetry"
    meta_desc = "General Bathymetric Chart of the Oceans (GEBCO)"
    meta_agency = "GEBCO / IHO / IOC"
    meta_tags = ["gebco", "bathymetry", "global", "wcs", "tid"]
    meta_region = "Global"
    meta_resolution = "15 arc-seconds (~500m)"
    meta_license = "Public Domain / Attribution"
    meta_urls = {"home": "https://www.gebco.net/"}

    def _get_gebco_url(self, layer, service):
        base = f"https://dap.ceda.ac.uk/thredds/{service}/bodc/gebco/global/gebco_{self.year}"
        if layer == "tid":
            return f"{base}/type_identifier_grid/netcdf/gebco_{self.year}_tid.nc"
        elif layer == "sub_ice":
            return f"{base}/sub_ice_topo/netcdf/GEBCO_{self.year}_sub_ice_topo.nc"
        return f"{base}/ice_surface_elevation/netcdf/GEBCO_{self.year}.nc"


class GEBCO(GEBCO_Base):
    """Fetch GEBCO bathymetry dynamically via THREDDS WCS."""

    name = "gebco"
    meta_category = "Bathymetry"
    meta_desc = "General Bathymetric Chart of the Oceans (GEBCO)"
    meta_agency = "GEBCO / IHO / IOC"
    meta_tags = ["gebco", "bathymetry", "global", "wcs", "tid"]
    meta_region = "Global"
    meta_resolution = "15 arc-seconds (~500m)"
    meta_license = "Public Domain / Attribution"
    meta_urls = {"home": "https://www.gebco.net/"}

    def __init__(self, layer="grid", include_tid=False, year="2026", **kwargs):
        super().__init__(name="gebco", **kwargs)
        self.layer = layer.lower()
        self.include_tid = str(include_tid).lower() in ["true", "1", "yes"]
        self.year = str(year)
        if self.min_year is not None or self.max_year is not None:
            self.year = min(
                [
                    int(x)
                    for x in [self.min_year, self.max_year, self.year]
                    if x is not None
                ]
            )

    def run(self):
        if not getattr(self, "region", None) or self.wgs_region.to_list() == [
            -180,
            180,
            -90,
            90,
        ]:
            logger.error(
                "You must provide a strict bounding region (-R) to use the WCS subsetter!"
            )
            return

        w, e, s, n = (
            self.wgs_region.xmin,
            self.wgs_region.xmax,
            self.wgs_region.ymin,
            self.wgs_region.ymax,
        )

        base_query = {
            "request": "GetCoverage",
            "version": "1.0.0",
            "service": "WCS",
            "bbox": self.wgs_region.format("bbox"),
            "format": "geotiff_float",
        }

        grid_base = self._get_gebco_url(self.layer, service="wcs")
        grid_query = base_query.copy()
        grid_query["coverage"] = "elevation"

        query_string = urllib.parse.urlencode(grid_query)
        grid_url = f"{grid_base}?{query_string}"
        grid_fn = f"gebco_{self.year}_{self.layer}_{w}_{e}_{s}_{n}.tif"

        self.add_entry_to_results(url=grid_url, dst_fn=grid_fn, data_type="rasterio")

        if self.include_tid:
            tid_base = self._get_gebco_url("tid", service="wcs")
            tid_query = base_query.copy()
            tid_query["coverage"] = "tid"

            tid_url = f"{tid_base}?{urllib.parse.urlencode(tid_query)}"
            tid_fn = f"gebco_{self.year}_tid_{w}_{e}_{s}_{n}.tif"

            self.add_entry_to_results(url=tid_url, dst_fn=tid_fn, data_type="rasterio")


class GEBCO_NCSS(GEBCO_Base):
    """Fetch GEBCO bathymetry dynamically via THREDDS NCSS."""

    name = "gebco_ncss"
    meta_category = "Bathymetry"
    meta_desc = "General Bathymetric Chart of the Oceans (GEBCO) via NCSS"
    meta_agency = "GEBCO / IHO / IOC"
    meta_tags = ["gebco", "bathymetry", "global", "ncss", "tid"]
    meta_region = "Global"
    meta_resolution = "15 arc-seconds (~500m)"
    meta_license = "Public Domain / Attribution"
    meta_urls = {"home": "https://www.gebco.net/"}

    def __init__(self, layer="grid", include_tid=False, year="2026", **kwargs):
        super().__init__(name="gebco_ncss", **kwargs)
        self.layer = layer.lower()
        self.include_tid = str(include_tid).lower() in ["true", "1", "yes"]
        self.year = str(year)

    def run(self):
        if not getattr(self, "region", None) or self.wgs_region.to_list() == [
            -180,
            180,
            -90,
            90,
        ]:
            logger.error(
                "You must provide a strict bounding region (-R) to use the NCSS subsetter!"
            )
            return

        w, e, s, n = (
            self.wgs_region.xmin,
            self.wgs_region.xmax,
            self.wgs_region.ymin,
            self.wgs_region.ymax,
        )

        base_query = {
            "north": n,
            "south": s,
            "west": w,
            "east": e,
            "accept": "netcdf",
        }

        grid_base = self._get_gebco_url(self.layer, service="ncss")
        grid_query = base_query.copy()
        grid_query["var"] = "elevation"

        grid_url = f"{grid_base}?{urllib.parse.urlencode(grid_query)}"
        grid_fn = f"gebco_{self.year}_{self.layer}_{w}_{e}_{s}_{n}.nc"

        self.add_entry_to_results(url=grid_url, dst_fn=grid_fn, data_type="netcdf")

        if self.include_tid:
            tid_base = self._get_gebco_url("tid", service="ncss")
            tid_query = base_query.copy()
            tid_query["var"] = "tid"

            tid_url = f"{tid_base}?{urllib.parse.urlencode(tid_query)}"
            tid_fn = f"gebco_{self.year}_tid_{w}_{e}_{s}_{n}.nc"

            self.add_entry_to_results(url=tid_url, dst_fn=tid_fn, data_type="netcdf")


class GEBCO_OpenDAP(GEBCO_Base):
    """Fetch GEBCO bathymetry dynamically via OpenDAP HTTP Subsetting.
    Requires ZERO external dependencies (No GDAL required).
    """

    name = "gebco_opendap"
    meta_category = "Bathymetry"
    meta_desc = "GEBCO via OpenDAP Array Subsetting"
    meta_agency = "GEBCO / IHO / IOC"
    meta_tags = ["gebco", "bathymetry", "global", "opendap", "tid"]
    meta_region = "Global"
    meta_resolution = "15 arc-seconds (~500m)"
    meta_license = "Public Domain / Attribution"
    meta_urls = {"home": "https://www.gebco.net/"}

    def __init__(self, layer="grid", include_tid=False, year="2026", **kwargs):
        super().__init__(name="gebco_opendap", **kwargs)
        self.layer = layer.lower()
        self.include_tid = str(include_tid).lower() in ["true", "1", "yes"]
        self.year = str(year)

    def run(self):
        if not getattr(self, "region", None) or self.wgs_region.to_list() == [
            -180,
            180,
            -90,
            90,
        ]:
            logger.error(
                "You must provide a strict bounding region (-R) to use the OpenDAP subsetter!"
            )
            return

        w, e, s, n = (
            self.wgs_region.xmin,
            self.wgs_region.xmax,
            self.wgs_region.ymin,
            self.wgs_region.ymax,
        )

        x1 = max(0, int(math.floor((w + 180) * 240)))
        x2 = min(86400, int(math.ceil((e + 180) * 240)))

        y1 = max(0, int(math.floor((s + 90) * 240)))
        y2 = min(43200, int(math.ceil((n + 90) * 240)))

        grid_base = self._get_gebco_url(self.layer, service="dodsC")
        z_var = "elevation"

        grid_query = (
            f"?{z_var}[{y1}:1:{y2}][{x1}:1:{x2}],lat[{y1}:1:{y2}],lon[{x1}:1:{x2}]"
        )
        grid_url = f"{grid_base}.dods{grid_query}"

        grid_fn = f"gebco_{self.year}_{self.layer}_{w}_{e}_{s}_{n}.nc"

        self.add_entry_to_results(url=grid_url, dst_fn=grid_fn, data_type="netcdf")

        if self.include_tid:
            tid_base = self._get_gebco_url("tid", service="dodsC")
            tid_query = (
                f"?tid[{y1}:1:{y2}][{x1}:1:{x2}],lat[{y1}:1:{y2}],lon[{x1}:1:{x2}]"
            )
            tid_url = f"{tid_base}.nc{tid_query}"
            tid_fn = f"gebco_{self.year}_tid_{w}_{e}_{s}_{n}.nc"
            self.add_entry_to_results(url=tid_url, dst_fn=tid_fn, data_type="netcdf")
