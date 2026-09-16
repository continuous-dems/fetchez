#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_ds487
~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Data Series 487 (High-Resolution Coastal Bathymetry) module using FRED.
"""

import logging
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from fetchez import core
from fetchez import fred
from fetchez.modules.base import FetchModule
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

DS487_BASE_URL = "https://pubs.usgs.gov/ds/487/"
DS487_DEMS_URL = f"{DS487_BASE_URL}data/DEMs/"
DS487_META_URL = f"{DS487_BASE_URL}metadata/"
DS487_METADATA_URL = f"{DS487_META_URL}DEM_fullmetadata.xml"

# USGS DS 487 states that all 45 DEMs use NAD83 / UTM Zone 11N.
# EPSG:26911 is NAD83 / UTM zone 11N.
DS487_CRS = "EPSG:26911"

# Published overall geographic extent.
DS487_EXTENT = (-120.511, 32.518, -117.033, 34.494)  # west, south, east, north
DS487_EXTENT_TOLERANCE = 0.25


class USGS_DS487(FetchModule):
    name = "usgs_ds487"
    meta_category = "Bathymetry"
    meta_desc = "USGS Data Series 487: High-Resolution Coastal Bathymetry"
    meta_agency = "USGS"
    meta_resolution = "3 m"
    meta_license = "Public Domain"
    meta_tags = ["california", "bathymetry", "coastal", "usgs", "dem"]

    def __init__(self, update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.force_update = update

        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    @staticmethod
    def _is_plausible_wgs84_bounds(bounds: tuple[float, float, float, float]) -> bool:
        """Return True when transformed bounds look plausible for DS 487."""
        west, south, east, north = bounds

        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            return False

        ds_w, ds_s, ds_e, ds_n = DS487_EXTENT
        tol = DS487_EXTENT_TOLERANCE
        return not (
            east < ds_w - tol
            or west > ds_e + tol
            or north < ds_s - tol
            or south > ds_n + tol
        )

    @staticmethod
    def _safe_raster_members(archive: zipfile.ZipFile, dataset_name: str):
        """Yield likely raster members in a stable preference order.

        DS 487 is distributed primarily as Arc ASCII grids.  Some archives may
        also contain metadata text.
        """
        candidates = []
        suffix_rank = {".tif": 0, ".tiff": 0, ".img": 1, ".asc": 2, ".txt": 3}

        for info in archive.infolist():
            if info.is_dir():
                continue

            member = Path(info.filename)
            suffix = member.suffix.lower()
            if suffix not in suffix_rank:
                continue

            stem_matches = member.stem.lower() == dataset_name.lower()
            candidates.append(
                (
                    0 if stem_matches else 1,
                    suffix_rank[suffix],
                    -info.file_size,
                    info,
                )
            )

        for _, _, _, info in sorted(candidates, key=lambda item: item[:3]):
            yield info

    @staticmethod
    def _extract_member(
        archive: zipfile.ZipFile,
        member: zipfile.ZipInfo,
        destination: Path,
    ) -> Path:
        """Extract one archive member without trusting its archive path."""
        output = destination / Path(member.filename).name
        with archive.open(member) as src, output.open("wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
        return output

    def _geometry_from_archive(self, zip_path: Path, dataset_name: str):
        """Read a DEM archive and return its WGS84 bounding-box geometry."""
        import rasterio
        from rasterio.crs import CRS
        from rasterio.errors import RasterioIOError
        from rasterio.warp import transform_bounds
        from shapely.geometry import box, mapping

        fallback_crs = CRS.from_user_input(DS487_CRS)

        with zipfile.ZipFile(zip_path) as archive:
            with tempfile.TemporaryDirectory(
                prefix=f"ds487-{dataset_name}-"
            ) as extract_dir:
                extract_path = Path(extract_dir)

                for member in self._safe_raster_members(archive, dataset_name):
                    raster_path = self._extract_member(archive, member, extract_path)

                    try:
                        with rasterio.open(raster_path) as src:
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
                    except RasterioIOError:
                        logger.debug(
                            "[%s] Archive member %s is not a readable raster; trying next member.",
                            self.name,
                            member.filename,
                        )
                        continue
                    except Exception as exc:
                        logger.debug(
                            "[%s] Failed reading %s from %s: %s",
                            self.name,
                            member.filename,
                            zip_path.name,
                            exc,
                        )
                        continue

                    if not self._is_plausible_wgs84_bounds(wgs84_bounds):
                        logger.warning(
                            "[%s] Ignoring implausible transformed bounds for %s: %s",
                            self.name,
                            dataset_name,
                            wgs84_bounds,
                        )
                        continue

                    west, south, east, north = wgs84_bounds
                    return mapping(box(west, south, east, north))

        return None

    def update_fred(self):
        """Build the DS 487 FRED index from the 45 downloadable DEM archives."""
        logger.info("Building FRED index for USGS DS 487. This may take a moment...")

        dems_page = core.Fetch(DS487_DEMS_URL).fetch_html()
        if dems_page is None:
            logger.error("[%s] Failed to fetch DS 487 DEM listing.", self.name)
            return

        zip_links = sorted(
            {
                href
                for href in dems_page.xpath('//a[contains(@href, ".zip")]/@href')
                if Path(href).suffix.lower() == ".zip"
            }
        )

        if not zip_links:
            logger.error(
                "[%s] No DEM ZIP archives found at %s", self.name, DS487_DEMS_URL
            )
            return

        existing_ids = {
            feature.get("properties", {}).get("ID") for feature in self.FRED.features
        }

        count = 0
        with tempfile.TemporaryDirectory(prefix="fetchez-ds487-") as temp_dir:
            temp_path = Path(temp_dir)

            with tqdm(
                total=len(zip_links),
                desc="Parsing DS 487 datasets",
                disable=self.silent,
            ) as pbar:
                for zip_href in zip_links:
                    try:
                        dataset_name = Path(zip_href).stem
                        if dataset_name in existing_ids:
                            continue

                        zip_url = urljoin(DS487_DEMS_URL, zip_href)
                        zip_path = temp_path / Path(zip_href).name

                        logger.debug("[%s] Downloading %s", self.name, zip_url)
                        fetched = core.Fetch(zip_url).fetch_file(
                            str(zip_path), verbose=False
                        )

                        # fetch_file implementations differ on whether they
                        # return a path/value.  The file on disk is the source
                        # of truth here.
                        if not zip_path.exists():
                            logger.warning(
                                "[%s] Download did not produce %s (return value: %r)",
                                self.name,
                                zip_path,
                                fetched,
                            )
                            continue

                        try:
                            geom = self._geometry_from_archive(zip_path, dataset_name)
                        except zipfile.BadZipFile:
                            logger.warning(
                                "[%s] Invalid ZIP archive: %s", self.name, zip_url
                            )
                            continue

                        if geom is None:
                            logger.warning(
                                "[%s] Could not determine geometry for %s",
                                self.name,
                                dataset_name,
                            )
                            continue

                        self.FRED.add_survey(
                            geom=geom,
                            Name=dataset_name,
                            ID=dataset_name,
                            Agency="USGS",
                            DataLink=zip_url,
                            MetadataLink=DS487_METADATA_URL,
                            DataType="rio",
                            DataSource=self.name,
                            Info="USGS DS 487, 3 m coastal DEM",
                        )
                        existing_ids.add(dataset_name)
                        count += 1

                    except Exception as exc:
                        logger.warning(
                            "[%s] Failed to index %s: %s",
                            self.name,
                            zip_href,
                            exc,
                        )
                    finally:
                        pbar.update()

        if count > 0:
            logger.info("Added %d new DS 487 datasets to FRED.", count)
            self.FRED.save()
        else:
            logger.info("No new DS 487 datasets were added to FRED.")

    def run(self):
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info("No matching USGS DS 487 datasets found for this region.")
            return self

        for surv in results:
            data_link = surv.get("DataLink")
            if not data_link:
                continue

            self.add_entry_to_results(
                url=data_link,
                dst_fn=Path(data_link).name,
                data_type=surv.get("DataType", "rio"),
                info=surv.get("Info", ""),
            )

        return self
