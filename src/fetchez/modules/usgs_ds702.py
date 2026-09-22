#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.usgs_ds702
~~~~~~~~~~~~~~~~~~~~~~~~~~

USGS Data Series 702:
Bathymetry and Acoustic Backscatter--Outer Mainland Shelf,
Eastern Santa Barbara Channel, California.

Bathymetry-only FRED module indexing the seven survey blocks and the
10 m merged Santa Barbara Channel bathymetry grid.
"""

import logging
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from fetchez import core
from fetchez import fred
from fetchez.modules.base import FetchModule
from fetchez.utils import str_or
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

DS702_BASE_URL = "https://pubs.usgs.gov/ds/702/"
DS702_DATA_URL = f"{DS702_BASE_URL}data.html"
DS702_BATHY_METADATA_URL = (
    f"{DS702_BASE_URL}metadata/bathymetry_metadata/bathy_metadata.xml"
)
DS702_MERGED_METADATA_URL = (
    f"{DS702_BASE_URL}"
    "metadata/merged_SBChannel_metadata/merged_SBChannel_bathy_metadata.xml"
)

# All distributed grids are NAD83 / UTM zone 11N.
DS702_CRS = "EPSG:26911"


class USGS_DS702(FetchModule):
    """Fetch USGS DS 702 Santa Barbara Channel bathymetry."""

    name = "usgs_ds702"
    meta_category = "Bathymetry"
    meta_desc = (
        "USGS Data Series 702: Eastern Santa Barbara Channel bathymetry "
        "and 10 m merged bathymetric DTM"
    )
    meta_agency = "USGS"
    meta_resolution = "Varies; 10 m merged DTM"
    meta_license = "Public Domain"
    meta_tags = [
        "california",
        "santa_barbara_channel",
        "bathymetry",
        "coastal",
        "usgs",
        "dem",
    ]
    meta_urls = {
        "publication": DS702_BASE_URL,
        "data": DS702_DATA_URL,
    }

    def __init__(self, datatype: str = "all", update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.datatype = str_or(datatype, "all").lower()
        self.force_update = update

        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    @staticmethod
    def _safe_raster_members(archive: zipfile.ZipFile):
        """Yield likely raster members in a stable preference order."""
        suffix_rank = {
            ".tif": 0,
            ".tiff": 0,
            ".img": 1,
            ".asc": 2,
            ".grd": 3,
            ".txt": 4,
        }
        candidates = []

        for info in archive.infolist():
            if info.is_dir():
                continue

            suffix = Path(info.filename).suffix.lower()
            if suffix not in suffix_rank:
                continue

            candidates.append((suffix_rank[suffix], -info.file_size, info))

        for _, _, info in sorted(candidates, key=lambda item: item[:2]):
            yield info

    @staticmethod
    def _extract_member(
        archive: zipfile.ZipFile,
        member: zipfile.ZipInfo,
        destination: Path,
    ) -> Path:
        """Extract one member without trusting archive paths."""
        output = destination / Path(member.filename).name
        with archive.open(member) as src, output.open("wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
        return output

    def _geometry_from_archive(self, zip_path: Path):
        """Return a WGS84 footprint from the first readable raster in a ZIP."""
        import rasterio
        from rasterio.crs import CRS
        from rasterio.errors import RasterioIOError
        from rasterio.warp import transform_bounds
        from shapely.geometry import box, mapping

        fallback_crs = CRS.from_user_input(DS702_CRS)

        with zipfile.ZipFile(zip_path) as archive:
            with tempfile.TemporaryDirectory(prefix="fetchez-ds702-raster-") as td:
                extract_dir = Path(td)

                for member in self._safe_raster_members(archive):
                    raster_path = self._extract_member(archive, member, extract_dir)

                    try:
                        with rasterio.open(raster_path) as src:
                            src_crs = src.crs or fallback_crs
                            bounds = src.bounds

                            west, south, east, north = transform_bounds(
                                src_crs,
                                "EPSG:4326",
                                bounds.left,
                                bounds.bottom,
                                bounds.right,
                                bounds.top,
                                densify_pts=21,
                            )
                            return mapping(box(west, south, east, north))

                    except RasterioIOError:
                        logger.debug(
                            "[%s] %s is not a readable raster; trying next member.",
                            self.name,
                            member.filename,
                        )
                    except Exception as exc:
                        logger.debug(
                            "[%s] Failed reading %s from %s: %s",
                            self.name,
                            member.filename,
                            zip_path.name,
                            exc,
                        )

        return None

    @staticmethod
    def _classify_dataset(filename: str) -> str | None:
        """Return DS702 logical datatype for a bathymetry archive."""
        name = filename.lower()

        if name == "sbchannel_10mbathy.zip":
            return "merged"

        if name.startswith("block_") and name.endswith("_bathy.zip"):
            return "survey"

        return None

    def update_fred(self):
        """Build FRED entries from the DS702 bathymetry downloads."""
        logger.info("Building FRED index for USGS DS 702...")

        page = core.Fetch(DS702_DATA_URL).fetch_html()
        if page is None:
            logger.error("[%s] Failed to fetch DS 702 data catalog.", self.name)
            return

        links = sorted(
            {
                href
                for href in page.xpath('//a[contains(@href, ".zip")]/@href')
                if self._classify_dataset(Path(href).name) is not None
            }
        )

        if not links:
            logger.error("[%s] No DS 702 bathymetry archives found.", self.name)
            return

        existing_ids = {
            feature.get("properties", {}).get("ID") for feature in self.FRED.features
        }

        count = 0

        with tempfile.TemporaryDirectory(prefix="fetchez-ds702-") as td:
            temp_dir = Path(td)

            with tqdm(
                total=len(links),
                desc="Parsing DS 702 bathymetry",
                disable=self.silent,
            ) as pbar:
                for href in links:
                    try:
                        filename = Path(href).name
                        dataset_id = Path(filename).stem
                        datatype = self._classify_dataset(filename)

                        if dataset_id in existing_ids:
                            continue

                        data_url = urljoin(DS702_DATA_URL, href)
                        zip_path = temp_dir / filename

                        fetched = core.Fetch(data_url).fetch_file(
                            str(zip_path), verbose=False
                        )

                        if not zip_path.exists():
                            logger.warning(
                                "[%s] Download did not produce %s (return value: %r)",
                                self.name,
                                zip_path,
                                fetched,
                            )
                            continue

                        try:
                            geom = self._geometry_from_archive(zip_path)
                        except zipfile.BadZipFile:
                            logger.warning(
                                "[%s] Invalid ZIP archive: %s",
                                self.name,
                                data_url,
                            )
                            continue

                        if geom is None:
                            logger.warning(
                                "[%s] Could not determine geometry for %s",
                                self.name,
                                dataset_id,
                            )
                            continue

                        is_merged = datatype == "merged"
                        metadata_url = (
                            DS702_MERGED_METADATA_URL
                            if is_merged
                            else DS702_BATHY_METADATA_URL
                        )
                        info = (
                            "USGS DS 702, 10 m merged Santa Barbara Channel DTM"
                            if is_merged
                            else "USGS DS 702, eastern Santa Barbara Channel bathymetry"
                        )

                        self.FRED.add_survey(
                            geom=geom,
                            Name=dataset_id,
                            ID=dataset_id,
                            Agency="USGS",
                            DataLink=data_url,
                            MetadataLink=metadata_url,
                            DataType=datatype,
                            DataSource=self.name,
                            Info=info,
                        )

                        existing_ids.add(dataset_id)
                        count += 1

                    except Exception as exc:
                        logger.warning(
                            "[%s] Failed to index %s: %s",
                            self.name,
                            href,
                            exc,
                        )
                    finally:
                        pbar.update()

        if count > 0:
            logger.info("Added %d new DS 702 datasets to FRED.", count)
            self.FRED.save()
        else:
            logger.info("No new DS 702 datasets were added to FRED.")

    def run(self):
        """Return DS702 bathymetry archives intersecting the requested region."""
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info(
                "[%s] No matching DS 702 bathymetry found for this region.",
                self.name,
            )
            return self

        for surv in results:
            datatype = str(surv.get("DataType", "")).lower()

            if self.datatype not in ("all", datatype):
                continue

            data_link = surv.get("DataLink")
            if not data_link:
                continue

            self.add_entry_to_results(
                url=data_link,
                dst_fn=Path(data_link).name,
                data_type="rio",
                title=surv.get("Name"),
                hdatum="NAD83 / UTM zone 11N",
                vdatum="NAVD88",
                info=surv.get("Info", ""),
            )

        return self
