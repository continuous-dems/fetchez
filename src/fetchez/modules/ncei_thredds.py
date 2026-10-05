#!/usr/bin/env python

"""
fetchez.modules.copernicus
~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch data from the NCEI THREDDS Server.

:copyright: (c) 2022 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlencode

from shapely.geometry import shape

from fetchez import core, spatial
from fetchez.modules.base import FetchModule

logger = logging.getLogger(__name__)

NGDC_BASE_URL = "https://www.ngdc.noaa.gov"
DEFAULT_THREDDS_BASE = "https://www.ngdc.noaa.gov/thredds/catalog/"
DEFAULT_THREDDS_SUFFIX = "/catalog.xml"
DEFAULT_CATALOG_URL = "https://www.ngdc.noaa.gov/thredds/catalog/regional/catalog.xml"
DEFAULT_CATALOG = "regional"
CATALOGS = ["regional", "tiles", "global", "pmel"]


class NCEIThredds(FetchModule):
    name = "ncei_thredds"
    meta_category = "Topography"
    meta_desc = "Dynamically fetch NOAA NCEI DEMs via THREDDS Catalogs."
    meta_agency = "NOAA NCEI"
    meta_license = "Public Domain"
    meta_resolution = "Varies"
    meta_tags = ["dem", "coastal", "bathymetry", "thredds", "ngdc"]

    def __init__(
        self,
        catalog_url: str | None = None,
        catalog: str = DEFAULT_CATALOG,
        dataset: str | None = None,
        want_wcs: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.catalog = catalog
        self.dataset_filter = dataset
        self.want_wcs = want_wcs

        if self.catalog and not catalog_url and self.catalog in CATALOGS:
            self.catalog_url = (
                f"{DEFAULT_THREDDS_BASE}{self.catalog}{DEFAULT_THREDDS_SUFFIX}"
            )
        else:
            self.catalog_url = catalog_url or DEFAULT_CATALOG_URL
        self.catalog_url = self.catalog_url.replace(".html", ".xml")

    def _extract_vdatum(self, name: str) -> str:
        name_lower = name.lower()
        if "navd88" in name_lower:
            return "vdatum:navd88"
        if "mhhw" in name_lower:
            return "vdatum:mhhw"
        if "mhw" in name_lower:
            return "vdatum:mhw"
        if "mllw" in name_lower:
            return "vdatum:mllw"
        if "msl" in name_lower:
            return "vdatum:msl"
        return "Unknown"

    def _extract_year(self, name: str) -> int | None:
        match = re.search(r"(?:_|\b)(19\d{2}|20\d{2})(?:_|\b)", name)
        if match:
            return int(match.group(1))
        return None

    def _parse_catalog(self, url: str) -> list[dict]:
        datasets: list[dict] = []
        try:
            xml_doc = core.Fetch(url).fetch_xml()
            if xml_doc is None:
                return datasets

            ds_nodes = xml_doc.findall(".//th:dataset", namespaces=core.NAMESPACES)
            services = xml_doc.findall(".//th:service", namespaces=core.NAMESPACES)

            for ds in ds_nodes:
                ds_name = ds.attrib.get("name", "")
                ds_id = ds.attrib.get("ID", "")
                url_path = ds.attrib.get("urlPath")

                if (
                    self.dataset_filter
                    and self.dataset_filter.lower() not in ds_name.lower()
                ):
                    continue
                if not url_path:
                    continue

                iso_url, http_url, wcs_url = None, None, None

                for srv in services:
                    s_name = srv.attrib.get("name")
                    s_base = srv.attrib.get("base")
                    if s_base:
                        full_url = f"{NGDC_BASE_URL}{s_base}{url_path}"
                        if s_name == "iso":
                            iso_url = full_url
                        elif s_name == "http":
                            http_url = full_url
                        elif s_name == "wcs":
                            wcs_url = full_url

                # Fast Path: Attempt to extract geospatial bounds natively from the THREDDS catalog
                ds_bounds = None
                geo_node = ds.find(
                    "./th:geospatialCoverage", namespaces=core.NAMESPACES
                )
                if geo_node is not None:
                    try:
                        ns = geo_node.find(
                            "./th:northsouth", namespaces=core.NAMESPACES
                        )
                        ew = geo_node.find("./th:eastwest", namespaces=core.NAMESPACES)

                        s_start = float(
                            ns.find("./th:start", namespaces=core.NAMESPACES).text
                        )
                        s_size = float(
                            ns.find("./th:size", namespaces=core.NAMESPACES).text
                        )
                        e_start = float(
                            ew.find("./th:start", namespaces=core.NAMESPACES).text
                        )
                        e_size = float(
                            ew.find("./th:size", namespaces=core.NAMESPACES).text
                        )

                        ds_bounds = [
                            e_start,
                            e_start + e_size,
                            s_start,
                            s_start + s_size,
                        ]
                    except Exception:
                        pass

                datasets.append(
                    {
                        "name": ds_name,
                        "id": ds_id,
                        "iso_url": iso_url,
                        "http_url": http_url,
                        "wcs_url": wcs_url,
                        "bounds": ds_bounds,
                    }
                )

            cat_refs = xml_doc.findall(".//th:catalogRef", namespaces=core.NAMESPACES)
            for ref in cat_refs:
                href = ref.attrib.get("{http://www.w3.org/1999/xlink}href")
                if href:
                    next_url = (
                        f"{NGDC_BASE_URL}{href}"
                        if href.startswith("/")
                        else f"{Path(url).parent}/{href}"
                    )
                    datasets.extend(self._parse_catalog(next_url))

        except Exception as e:
            logger.warning(f"Failed to parse catalog {url}: {e}")

        return datasets

    def run(self):
        logger.info(f"Scanning THREDDS catalog: {self.catalog_url}")

        all_datasets = self._parse_catalog(self.catalog_url)
        search_shape = (
            spatial.region_to_shapely(self.wgs_region) if self.wgs_region else None
        )

        for ds in all_datasets:
            ds_name = ds["name"]

            ds_year = self._extract_year(ds_name)
            if ds_year:
                if self.min_year and ds_year < self.min_year:
                    continue
                if self.max_year and ds_year > self.max_year:
                    continue

            if search_shape:
                ds_shape = None

                # 1. Use fast bounds from THREDDS catalog XML
                if ds.get("bounds"):
                    w, e, s, n = ds["bounds"]
                    ds_shape = spatial.Region(w, e, s, n).to_shapely()

                # 2. Fallback to updated ISO Metadata XML
                elif ds["iso_url"]:
                    iso_meta = core.iso_xml(ds["iso_url"])
                    if iso_meta.xml_doc is not None:
                        geom = iso_meta.polygon(geom=True)
                        if geom:
                            ds_shape = shape(geom)

                # FAIL CLOSED: If we still have no bounds, or they don't intersect, skip it.
                if ds_shape is None or not search_shape.intersects(ds_shape):
                    continue

            vdatum = self._extract_vdatum(ds_name)

            if self.want_wcs and ds["wcs_url"] and self.wgs_region:
                wcs_params = {
                    "request": "GetCoverage",
                    "version": "1.0.0",
                    "service": "WCS",
                    "coverage": "z",
                    "bbox": self.wgs_region.format("bbox"),
                    "format": "geotiff_float",
                }
                query_string = urlencode(wcs_params)
                download_url = f"{ds['wcs_url']}?{query_string}"
                out_fn = ds_name.replace(".nc", ".tif")

                self.add_entry_to_results(
                    url=download_url,
                    dst_fn=out_fn,
                    data_type="raster",
                    vdatum=vdatum,
                    year=ds_year,
                )

            elif ds["http_url"]:
                self.add_entry_to_results(
                    url=ds["http_url"],
                    dst_fn=ds_name,
                    data_type="raster",
                    vdatum=vdatum,
                    year=ds_year,
                )

        return self
