#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_of1221
~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Open Record 1211 (High-Resolution Coastal Bathymetry) module using FRED.
"""

import logging
from urllib.parse import urljoin
from pathlib import Path
import tarfile
import tempfile
import zipfile
import io

from fetchez import core
from fetchez import fred
from fetchez.utils import str_or
from fetchez.modules.base import FetchModule
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

OF1221_BASE_URL = "http://pubs.usgs.gov/of/2004/1221/"
OF1221_XYZ_BASE_URL = "https://pubs.usgs.gov/of/2004/1221/dataxyz.html"
OF1221_GRD_BASE_URL = "https://pubs.usgs.gov/of/2004/1221/datagrd.html"
OF1221_METADATA_URL = "https://pubs.usgs.gov/of/2004/1221/"
OF1221_CRS = "EPSG:26911"


class USGS_DS781(FetchModule):
    name = "usgs_of1221"
    meta_category = "Bathymetry"
    meta_desc = "Los Angeles and San Diego Margin High-Resolution Multibeam Bathymetry and Backscatter Data"
    meta_agency = "USGS"
    meta_resolution = "Varies"
    meta_license = "Public Domain"
    meta_tags = ["california", "bathymetry", "coastal", "usgs"]

    def __init__(self, datatype=None, update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.force_update = update
        self.datatype = str_or(datatype)

        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    def _geometry_from_archive(self, archive_path: Path, dataset_name: str):
        """Read a DEM archive and return its WGS84 bounding-box geometry."""
        import rasterio
        from rasterio.crs import CRS
        from rasterio.errors import RasterioIOError
        from rasterio.warp import transform_bounds
        from shapely.geometry import box, mapping

        fallback_crs = CRS.from_user_input(OF1221_CRS)
        grid_path = None
        with tempfile.TemporaryDirectory(prefix="fetchez-of1221-") as temp_dir:
            extract_path = Path(temp_dir)
            with zipfile.ZipFile(archive_path, "r") as z:
                tar_filename = [f for f in z.namelist() if f.endswith(".tar")][0]
                tar_bytes = z.read(tar_filename)
                with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
                    for member in tar.getmembers():
                        if member.isfile() and member.name.endswith(".adf"):
                            grid_path = extract_path / Path(str(member.name)).parent
                            break
                    tar.extractall(path=extract_path)

                    if grid_path is not None:
                        try:
                            with rasterio.open(grid_path) as src:
                                src_crs = src.crs or fallback_crs
                                bounds = src.bounds

                                # Transform all edges densely rather than only the
                                # lower-left and upper-right corners.
                                wgs84_bounds = transform_bounds(
                                    src_crs,
                                    "EPSG:4326",
                                    bounds.left,
                                    bounds.bottom,
                                    bounds.right,
                                    bounds.top,
                                    densify_pts=21,
                                )
                                west, south, east, north = wgs84_bounds
                                return mapping(box(west, south, east, north))

                        except RasterioIOError:
                            logger.debug(
                                "[%s] Archive member %s is not a readable raster;",
                                self.name,
                                grid_path,
                            )
                        except Exception as exc:
                            logger.debug(
                                "[%s] Failed reading %s from %s: %s",
                                self.name,
                                grid_path,
                                archive_path.name,
                                exc,
                            )

        return None

    def update_fred(self):

        logger.info("Building FRED index for USGS DS 1221. This will take a moment...")

        main_page = core.Fetch(OF1221_BASE_URL).fetch_html()
        if main_page is None:
            logger.error("Failed to fetch DS 1221 main page.")
            return

        xml_links = main_page.xpath('//a[contains(@href, ".xml")]/@href')
        xml_links = list(set(xml_links))  # Remove duplicates

        count = 0

        xyz_page = core.Fetch(OF1221_XYZ_BASE_URL).fetch_html()
        zip_xyz_links = xyz_page.xpath('//a[contains(@href, ".zip")]/@href')

        grd_page = core.Fetch(OF1221_GRD_BASE_URL).fetch_html()
        zip_grd_links = grd_page.xpath('//a[contains(@href, ".tgz")]/@href')
        with tempfile.TemporaryDirectory(prefix="fetchez-ds487-") as temp_dir:
            temp_path = Path(temp_dir)
            with tqdm(
                total=len(zip_grd_links), desc="Parsing Margins", disable=self.silent
            ) as pbar:
                for i, link in enumerate(zip_grd_links):
                    pbar.update()
                    margin_tgz = urljoin(OF1221_BASE_URL, link)
                    margin_xyz = urljoin(OF1221_BASE_URL, zip_xyz_links[i])
                    tgz_path = temp_path / Path(margin_tgz).name
                    fetched = core.Fetch(margin_tgz).fetch_file(
                        str(tgz_path), verbose=True
                    )
                    dataset_name = Path(margin_tgz).stem
                    if not tgz_path.exists():
                        logger.warning(
                            "[%s] Download did not produce %s (return value: %r)",
                            self.name,
                            tgz_path,
                            fetched,
                        )
                        continue

                    try:
                        geom = self._geometry_from_archive(tgz_path, dataset_name)
                    except Exception:
                        logger.exception(
                            "[%s] Invalid TGZ archive: %s", self.name, tgz_path
                        )
                        continue

                    if geom:
                        self.FRED.add_survey(
                            geom=geom,
                            Name=dataset_name,
                            ID=dataset_name,
                            Agency="USGS",
                            DataLink=margin_tgz,
                            MetadataLink=OF1221_METADATA_URL,
                            DataType="grd",
                            DataSource=self.name,
                            Info="USGS DS 1221, 4 m coastal DEM",
                        )
                        self.FRED.add_survey(
                            geom=geom,
                            Name=dataset_name,
                            ID=dataset_name,
                            Agency="USGS",
                            DataLink=margin_xyz,
                            MetadataLink=OF1221_METADATA_URL,
                            DataType="xyz",
                            DataSource=self.name,
                            Info="USGS DS 1221, 4 m coastal DEM",
                        )
                        count += 1

        if count > 0:
            logger.info(f"Added {count} new datasets to FRED.")
            self.FRED.save()

    def run(self):
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info("No matching USGS DS 1221 datasets found for this region.")
            return self

        for surv in results:
            data_link = surv.get("DataLink")
            data_type = surv.get("DataType")
            if self.datatype is not None:
                if self.datatype != data_type:
                    continue
            if data_link:
                self.add_entry_to_results(
                    url=data_link,
                    dst_fn=data_link.split("/")[-1],
                    data_type=surv.get("DataType", "gridded"),
                    info=surv.get("Info", ""),
                )

        return self
