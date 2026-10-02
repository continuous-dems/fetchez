#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.dav
~~~~~~~~~~~~~~~~~~~

Fetch NOAA Lidar, Raster, and Imagery data via the Digital Coast
Data Access Viewer (DAV) API.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Dict, Optional, Any
import requests

from pyproj import CRS, Transformer
from pyogrio.raw import read

from fetchez import core
from fetchez.modules import FetchModule
from fetchez import utils
from fetchez import cli

from fetchez.modules.tnm import TheNationalMap

logger = logging.getLogger(__name__)

DAV_API_URL = "https://coast.noaa.gov/dataviewer/api/v1/search/missions"
DAV_HEADERS = {"Content-Type": "application/json"}


# =============================================================================
# DAV Module
# =============================================================================
@cli.cli_opts(
    help_text="NOAA Digital Coast (Data Access Viewer)",
    datatype='Data type: "lidar", "raster" (DEM), "imagery", "landcover"',
    title_filter="Filter results by dataset title (case-insensitive)",
    want_footprints="Fetch the dataset footprint (tile index) zip only",
    keep_footprints="Keep the downloaded tile index zip after processing",
)
class DAV(FetchModule):
    name = "dav"
    meta_category = "Multidisciplinary"
    meta_desc = "NOAA Digital Coast Data Access Viewer"
    meta_agency = "NOAA"
    meta_tags = ["noaa", "lidar", "imagery", "dem", "digital coast", "landcover"]
    meta_region = "USA"
    meta_resolution = "Variable"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://coast.noaa.gov/dataviewer/"}
    meta_aliases = ["digital_coast"]

    """
    Fetch NOAA Lidar, Elevation, and Imagery.

    Uses the Digital Coast Data Access Viewer (DAV) API to discover datasets
    intersecting the region, downloads their tile indices (shapefiles), and
    extracts the URLs for specific data tiles.
    """

    def __init__(
        self,
        survey_id: Optional[str] = None,
        datatype: Optional[str] = "lidar",
        title_filter: Optional[str] = None,
        want_footprints: bool = False,
        keep_footprints: bool = False,
        name: Optional[str] = "dav",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.survey_id = survey_id
        self.datatype = datatype.lower() if datatype else "lidar"
        self.title_filter = title_filter
        self.want_footprints = want_footprints
        self.keep_footprints = keep_footprints

    def _region_to_ewkt(self):
        """Convert the current region to NAD83 (SRID 4269) EWKT Polygon string."""

        if self.wgs_region is None:
            return None

        w, e, s, n = self.wgs_region

        # Construct WKT Polygon (Counter-Clockwise)
        # DAV API expects SRID=4269 (NAD83)
        poly = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"
        return f"SRID=4269;{poly}"

    def _get_features(self) -> List[Dict[Any, Any]]:
        """Query the DAV API for missions in the region."""

        if self.wgs_region is None:
            return []

        dt_map = {
            "lidar": "Lidar",
            "raster": "DEM",
            "dem": "DEM",
            "elevation": "DEM",
            "imagery": "Imagery",
            "landcover": "Land Cover",
        }

        req_type = dt_map.get(self.datatype, "Lidar")
        req_types = [req_type]

        payload = {
            "aoi": self._region_to_ewkt(),
            "published": "true",
            "dataTypes": req_types,
        }

        try:
            r = requests.post(
                DAV_API_URL, json=payload, headers=DAV_HEADERS, timeout=20
            )
            r.raise_for_status()
            response = r.json()
            return response.get("data", {})
        except Exception as exception:
            logger.error(f"DAV API Query Error: {exception}")
            return []

    def _find_index_zip(self, bulk_url: str) -> Optional[str]:
        """Find the tile index zip file given the Bulk Download landing page URL."""

        try:
            page = core.Fetch(bulk_url).fetch_html()
        except Exception:
            return None

        if page is None:
            return None

        txt_links = page.xpath('//a[contains(@href, ".txt")]/@href')
        urllist_link = next((link for link in txt_links if "urllist" in link), None)

        index_zip_url = None

        if urllist_link:
            if not urllist_link.startswith("http"):
                urllist_link = urljoin(bulk_url, urllist_link)

            local_urllist = Path(self._outdir) / Path(urllist_link).name
            if core.Fetch(urllist_link).fetch_file(local_urllist, verbose=False) == 0:
                try:
                    with open(local_urllist, "r") as f:
                        for line in f:
                            if "tileindex" in line and "zip" in line:
                                index_zip_url = line.strip()
                                break
                except Exception:
                    pass
                finally:
                    local_urllist.unlink(missing_ok=True)

        if not index_zip_url:
            zip_links = page.xpath('//a[contains(@href, ".zip")]/@href')
            tile_zip = next((link for link in zip_links if "tileindex" in link), None)
            if tile_zip:
                if not tile_zip.startswith("http"):
                    index_zip_url = urljoin(bulk_url, tile_zip)
                else:
                    index_zip_url = tile_zip

        return index_zip_url

    def _intersects(self, box_a, box_b):
        """Simple AABB intersection check: [xmin, ymin, xmax, ymax]."""

        return not (
            box_b[0] > box_a[2]
            or box_b[2] < box_a[0]
            or box_b[1] > box_a[3]
            or box_b[3] < box_a[1]
        )

    def _process_index_shapefile(
        self, shp_path: str, dataset_id: str, data_type: str, is_bathy: bool, year: str
    ):
        """Parse the downloaded index shapefile using PyShp + PyProj."""

        prj_path = shp_path.replace(".shp", ".prj")
        target_crs = None

        try:
            if Path(prj_path).exists():
                with open(prj_path, "r") as f:
                    wkt_text = f.read()
                target_crs = CRS.from_wkt(wkt_text)
            else:
                target_crs = CRS.from_epsg(4269)
        except Exception as exception:
            logger.warning(f"Could not parse PRJ, assuming WGS84: {exception}")
            target_crs = CRS.from_epsg(4326)

        w, e, s, n = self.wgs_region
        transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)

        corners = [
            transformer.transform(w, s),
            transformer.transform(w, n),
            transformer.transform(e, n),
            transformer.transform(e, s),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        search_bbox = [min(xs), min(ys), max(xs), max(ys)]
        try:
            bbox = (search_bbox[0], search_bbox[1], search_bbox[2], search_bbox[3])
            meta, fids, geometry_wkb, fields = read(shp_path, bbox=bbox)

            if len(geometry_wkb) > 0:
                col_names = [str(col).lower() for col in meta.get("fields", [])]

                # Iterate over the arrays to recreate the properties dictionary
                for i in range(len(geometry_wkb)):
                    props_lower = {
                        col.lower(): fields[n][i] for n, col in enumerate(col_names)
                    }

                    tile_name = (
                        props_lower.get("name")
                        or props_lower.get("location")
                        or props_lower.get("tile_name")
                        or props_lower.get("filename")
                    )
                    tile_url = (
                        props_lower.get("url")
                        or props_lower.get("path")
                        or props_lower.get("url_link")
                    )

                    if isinstance(tile_url, str):
                        tile_url = tile_url.rstrip()

                    if not tile_url or not tile_name:
                        continue

                    # Clean up URL (handle relative paths/missing filenames)
                    if not tile_url.endswith(str(tile_name)):
                        if tile_url.endswith("/"):
                            tile_url += str(tile_name)
                        elif not tile_url.lower().endswith(
                            Path(str(tile_name)).name.lower()
                        ):
                            tile_url = (
                                f"{tile_url.rstrip('/')}/{Path(str(tile_name)).name}"
                            )

                    _dst_fn = Path(str(dataset_id)) / Path(tile_url).name
                    self.add_entry_to_results(
                        url=tile_url,
                        dst_fn=str(_dst_fn),
                        data_type=data_type,
                        agency="NOAA Digital Coast",
                        title=f"Dataset {dataset_id}",
                        is_bathy=is_bathy,
                        year=year,
                        geometry=geometry_wkb[i],
                    )

        except Exception as e:
            logger.error(f"Pyogrio processing failed: {e}")

    def _extract_usgs_project(self, url):
        """Extract project from the bulk URL."""

        if "Projects/" in url:
            parts = url.split("Projects/")[-1]
            return parts.split("/")[0]
        return None

    def run(self):
        """Run the DAV fetching module."""

        if self.wgs_region is None:
            return []

        logger.debug(f"Querying Digital Coast API for {self.datatype}...")
        data = self._get_features()
        datasets = data.get("datasets", [])

        import re

        for dataset in datasets:
            attrs = dataset.get("attributes", {})
            name = attrs.get("title", "")
            year = attrs.get("year", "")

            years = []
            for source in [year, name]:
                if source:
                    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", str(source))
                    if matches:
                        years = [int(y) for y in matches]
                        break

            dataset["_parsed_year"] = max(years) if years else 0

        logger.debug(f"Found {len(datasets)} potential datasets.")

        for dataset in datasets:
            attrs = dataset.get("attributes", {})
            fid = attrs.get("id")
            name = attrs.get("title")
            year = attrs.get("year")
            f_datatype = attrs.get("dataType")
            links_list = attrs.get("links", [])
            description = attrs.get("projectDescription", "")
            if self.min_year or self.max_year:
                import re

                years = []

                # Check the 'year' key first, then fallback to the title
                for source in [year, name]:
                    if source:
                        matches = re.findall(r"\b(19\d{2}|20\d{2})\b", str(source))
                        if matches:
                            years = [int(y) for y in matches]
                            break

                if years:
                    dataset_year = max(years)

                    if self.min_year and dataset_year < self.min_year:
                        continue
                    if self.max_year and dataset_year > self.max_year:
                        continue
                else:
                    logger.debug(f"Could not parse year for DAV dataset {fid}.")

            if self.survey_id and (
                int(utils.str_or(self.survey_id, "").strip()) != int(fid.strip())
            ):
                continue

            if self.title_filter and self.title_filter.lower() not in name.lower():
                continue

            providers = attrs.get("providers", [])
            is_usgs = any(p.get("name") == "U.S. Geological Survey" for p in providers)
            is_bathy = "bathy" in name.lower() or "bathy" in description.lower()

            bulk_url = None
            for link_obj in links_list:
                if link_obj.get("linkTypeId") == "46":
                    bulk_url = link_obj.get("uri")
                    break

            if not bulk_url:
                continue

            if is_usgs:
                project_name = self._extract_usgs_project(bulk_url)

                if project_name:
                    logger.debug(
                        f"Routing USGS dataset '{project_name}' to TNM module..."
                    )

                    # dav_dir = self._outdir.rstrip(os.sep)
                    # base_dir = os.path.dirname(dav_dir)
                    # tnm_outdir = os.path.join(base_dir, "tnm")

                    if self.datatype == "lidar":
                        target_datasets = "11"  # Lidar Point Cloud
                    else:
                        # For DEMs, search both OPR (8) and 1-meter (2) to be safe
                        target_datasets = "8/2"

                    tnm_mod = TheNationalMap(
                        src_region=self.wgs_region,
                        # outdir=tnm_outdir,
                        datasets=target_datasets,
                        q=project_name,
                    )

                    tnm_mod.run()
                    self.results.extend(tnm_mod.results)

                    continue

            logger.debug(f"Processing: {name}...")

            index_zip_url = self._find_index_zip(bulk_url)

            if not index_zip_url:
                continue

            if self.want_footprints:
                _dst_fn = Path(str(fid)) / Path(index_zip_url).name
                self.add_entry_to_results(
                    url=index_zip_url,
                    dst_fn=str(_dst_fn),
                    data_type="footprint",
                    title=f"Footprint {name}",
                )
                continue

            surv_name = f"dav_{fid}"
            local_zip = Path(self._outdir) / f"tileindex_{surv_name}.zip"

            try:
                Path(self._outdir).mkdir(parents=True, exist_ok=True)

                if core.Fetch(index_zip_url).fetch_file(local_zip, verbose=False) == 0:
                    unzipped = utils.p_unzip(
                        local_zip, ["shp", "shx", "dbf", "prj"], outdir=self._outdir
                    )
                    shp_file = next((f for f in unzipped if f.endswith(".shp")), None)

                    if shp_file:
                        self._process_index_shapefile(
                            shp_file, fid, f_datatype, is_bathy, year
                        )

                    if not self.keep_footprints:
                        utils.remove_glob(local_zip)
                        for f in unzipped:
                            Path(f).unlink(missing_ok=True)
                else:
                    logger.warning(f"Failed to download index: {index_zip_url}")

            except Exception as e:
                logger.error(f"Error processing DAV dataset {fid}: {e}")

        return self


# =============================================================================
# Subclasses / Shortcuts
# =============================================================================
@cli.cli_opts(
    help_text="NOAA Sea Level Rise (SLR) DEMs",
    want_footprints="Fetch the dataset footprint (tile index) zip only",
    keep_footprints="Keep the downloaded tile index zip after processing",
)
class SLR(DAV):
    name = "slr"
    meta_category = "Topography"
    meta_desc = "NOAA Sea Level Rise DEMs"
    meta_agency = "NOAA"
    meta_tags = ["slr", "dem", "elevation", "coastal"]
    meta_region = "USA / Coastal"
    meta_resolution = "Various"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://coast.noaa.gov/slr/"}

    """Fetch NOAA Sea Level Rise (SLR) DEMs.

    This is a shortcut for the DAV module that specifically filters for
    'SLR' in the dataset title and requests DEM/Raster data.
    """

    def __init__(self, **kwargs):
        kwargs.pop("datatype", None)
        kwargs.pop("title_filter", None)

        super().__init__(name="slr", datatype="raster", title_filter="SLR", **kwargs)


@cli.cli_opts(
    help_text="USGS/NOAA Coastal National Elevation Database (CoNED)",
    want_footprints="Fetch the dataset footprint (tile index) zip only",
    keep_footprints="Keep the downloaded tile index zip after processing",
)
class CoNED(DAV):
    name = "coned"
    meta_category = "Topography"
    meta_desc = "Coastal National Elevation Database (CoNED)"
    meta_agency = "USGS / NOAA"
    meta_tags = ["coned", "topobathy", "dem"]
    meta_region = "USA / Coastal"
    meta_resolution = "1m - 3m"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://www.usgs.gov/core-science-systems/ngp/coned"}

    """Fetch CoNED Topobathymetric Models.

    This is a shortcut for the DAV module that filters for 'CoNED' data.
    """

    def __init__(self, **kwargs):
        kwargs.pop("datatype", None)
        kwargs.pop("title_filter", None)

        super().__init__(
            name="coned", datatype="raster", title_filter="CoNED", **kwargs
        )


@cli.cli_opts(
    help_text="CUDEM (Continuously Updated Digital Elevation Model)",
    want_footprints="Fetch the dataset footprint (tile index) zip only",
    keep_footprints="Keep the downloaded tile index zip after processing",
)
class CUDEM(DAV):
    name = "cudem"
    meta_category = "Bathymetry"
    meta_desc = "Continuously Updated DEM (CUDEM)"
    meta_agency = "NOAA"
    meta_tags = ["cudem", "bathymetry", "dem"]
    meta_region = "USA / Coastal"
    meta_resolution = "1/9 Arc-Second"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://coast.noaa.gov/digitalcoast/data/cudem.html"}

    """Fetch CUDEM Tiled DEMs via Digital Coast."""

    def __init__(self, **kwargs):
        kwargs.pop("datatype", None)
        kwargs.pop("title_filter", None)

        super().__init__(
            name="cudem", datatype="raster", title_filter="CUDEM", **kwargs
        )
