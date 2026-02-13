#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.earthdata
~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch data from NASA's EarthData CMR (Common Metadata Repository)
and Harmony API.

Supports standard granule search and Harmony subsetting services.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import time
import datetime
import logging
from typing import List, Dict, Optional, Any, Union

from fetchez import core
from fetchez import utils
from fetchez import spatial
from fetchez import cli

try:
    from shapely.geometry import Polygon, box

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)

CMR_SEARCH_URL = "https://cmr.earthdata.nasa.gov/search/granules.json?"
HARMONY_BASE_URL = "https://harmony.earthdata.nasa.gov"


# =============================================================================
# EarthData Module
# =============================================================================
@cli.cli_opts(
    help_text="NASA EarthData (CMR / Harmony)",
    short_name="Dataset Short Name (e.g. ATL03, ATL08, MUR-JPL-L4-GLOB-v4.1)",
    provider="Data Provider (e.g. NSIDC_CPRD)",
    version="Dataset Version (e.g. 006)",
    time_start="Start Date (ISO 8601: 2020-01-01T00:00:00Z)",
    time_end="End Date (ISO 8601: 2020-02-01T00:00:00Z)",
    subset="Use Harmony API for subsetting (if supported)",
    filename_filter="Filter granules by filename pattern (wildcards supported)",
)
class EarthData(core.FetchModule):
    """Access NASA Earth Science Data via CMR and Harmony.

    NASA promotes the full and open sharing of all its data.
    Requires ~/.netrc credentials or interactive login.
    """

    def __init__(
        self,
        short_name: str = "ATL03",
        provider: str = "",
        time_start: str = "",
        time_end: str = "",
        version: str = "",
        filename_filter: Optional[str] = None,
        subset: bool = False,
        subset_job_id: Optional[str] = None,
        harmony_ping: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(name="cmr", **kwargs)
        self.short_name = short_name
        self.provider = provider
        self.time_start = time_start
        self.time_end = time_end
        self.version = version
        self.filename_filter = filename_filter
        self.subset = subset
        self.subset_job_id = subset_job_id
        self.harmony_ping = harmony_ping  # 'status', 'pause', 'resume', 'cancel'

        # URLs
        self._cmr_url = CMR_SEARCH_URL
        self._harmony_url = (
            f"{HARMONY_BASE_URL}/ogc-api-edr/1.1.0/collections/{short_name}/cube?"
        )

        # Authentication
        credentials = core.get_credentials("https://urs.earthdata.nasa.gov")
        if credentials:
            self.headers = {
                "Authorization": f"Basic {credentials}",
                "User-Agent": core.DEFAULT_USER_AGENT,
            }
        else:
            self.headers = {}
            logger.warning(
                "Could not retrieve EarthData credentials. Public data might fail."
            )

    def add_wildcards_to_str(self, in_str: str) -> str:
        """Ensure wildcards exist at start/end of string."""

        if not in_str.startswith("*"):
            in_str = f"*{in_str}"
        if not in_str.endswith("*"):
            in_str = f"{in_str}*"
        return in_str

    def _format_date(self, date_str: str) -> str:
        """Formats an ISO date string for filtering."""

        if not date_str:
            return ".."
        try:
            if "T" not in date_str:
                date_str += "T00:00:00"
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", ""))
            return dt.isoformat(timespec="milliseconds") + "Z"
        except ValueError:
            return ".."

    def harmony_ping_for_status(
        self, job_id: str, ping_request: str = "status"
    ) -> Optional[Dict]:
        """Check status of a Harmony Job."""

        valid_requests = ["status", "pause", "resume", "cancel"]
        base_url = f"{HARMONY_BASE_URL}/jobs/{job_id}"

        if ping_request in valid_requests[1:]:
            status_url = f"{base_url}/{ping_request}"
        else:
            status_url = base_url

        req = core.Fetch(status_url, headers=self.headers).fetch_req(timeout=10)
        if req and req.status_code == 200:
            return req.json()
        return None

    def harmony_make_request(self) -> Optional[Dict]:
        """Initiate a Harmony Subset Request."""

        if not self.region:
            return None

        w, e, s, n = self.region
        harmony_data = {
            "bbox": f"{w},{s},{e},{n}",
        }

        start_t = self._format_date(self.time_start)
        end_t = self._format_date(self.time_end)

        if start_t != ".." or end_t != "..":
            harmony_data["datetime"] = f"{start_t}/{end_t}"

        logger.info(f"Submitting Harmony Request for {self.short_name}...")

        req = core.Fetch(self._harmony_url, headers=self.headers).fetch_req(
            params=harmony_data, timeout=30
        )

        if req and req.status_code in [200, 201, 202]:
            return req.json()

        logger.error(
            f"Harmony request failed: {req.status_code if req else 'No Response'}"
        )
        if req:
            logger.debug(req.text)
        return None

    def earthdata_set_config(self) -> Dict:
        """Configure CMR Search Parameters."""

        w, e, s, n = self.region

        data = {
            "provider": self.provider,
            "short_name": self.short_name,
            "bounding_box": f"{w},{s},{e},{n}",
            "temporal": f"{self.time_start},{self.time_end}",
            "page_size": 2000,
        }

        if self.version:
            data["version"] = self.version

        if "*" in self.short_name:
            data["options[short_name][pattern]"] = "true"

        if self.filename_filter:
            data["options[producer_granule_id][pattern]"] = "true"
            filters = self.filename_filter.split(",")
            for f in filters:
                data["producer_granule_id"] = self.add_wildcards_to_str(f)

        return data

    def _run_cmr_search(self):
        """Execute standard CMR Granule Search."""

        params = self.earthdata_set_config()
        logger.info(f"Searching CMR for {self.short_name}...")

        req = core.Fetch(self._cmr_url).fetch_req(params=params)

        if not req:
            logger.error("CMR Request failed.")
            return

        try:
            feed = req.json().get("feed", {})
            entries = feed.get("entry", [])
        except Exception as e:
            logger.error(f"Error parsing CMR response: {e}")
            return

        logger.info(f"CMR returned {len(entries)} potential granules.")

        # Prepare Shapely Polygon for precise filtering
        search_geom = None
        if HAS_SHAPELY:
            search_geom = spatial.region_to_shapely(self.region)

        for entry in entries:
            # Spatial Filtering (Refine BBox search)
            geom_valid = True

            # Check Polygon Intersection if Shapely available
            if HAS_SHAPELY and search_geom and "polygons" in entry:
                try:
                    # CMR Polygons are list of lists: [['lat1 lon1 lat2 lon2 ...']]
                    poly_str = entry["polygons"][0][0]
                    coords = [float(x) for x in poly_str.split()]

                    lats = coords[::2]
                    lons = coords[1::2]
                    points = list(zip(lons, lats))

                    granule_poly = Polygon(points)

                    if not search_geom.intersects(granule_poly):
                        geom_valid = False
                except Exception:
                    pass

            if geom_valid:
                for link in entry.get("links", []):
                    # Filter for direct data download links
                    if (
                        link.get("rel", "").endswith("/data#")
                        and "inherited" not in link
                    ):
                        href = link.get("href")
                        if href:
                            fname = href.split("/")[-1]

                            self.add_entry_to_results(
                                url=href,
                                dst_fn=fname,
                                data_type=self.short_name,
                                # Metadata
                                start_time=entry.get("time_start"),
                                end_time=entry.get("time_end"),
                                granule_size=entry.get("granule_size"),
                                dataset_id=entry.get("dataset_id"),
                            )

    def _run_harmony_subset(self):
        """Execute Harmony Subset Job."""

        if not self.subset_job_id:
            status = self.harmony_make_request()
            if status and "jobID" in status:
                self.subset_job_id = status["jobID"]
                logger.info(f"Harmony Job Initiated: {self.subset_job_id}")
            else:
                return

        if self.subset_job_id:
            logger.info(f"Polling Harmony Job {self.subset_job_id}...")

            while True:
                try:
                    status = self.harmony_ping_for_status(self.subset_job_id)
                    if not status:
                        time.sleep(10)
                        continue

                    progress = status.get("progress", 0)
                    state = status.get("status", "unknown")

                    if state == "successful":
                        logger.info("Harmony Job Successful. Processing links...")
                        for link in status.get("links", []):
                            href = link.get("href", "")
                            # Only grab data files
                            if href.endswith((".h5", ".nc", ".tif", ".tiff")):
                                base_name = os.path.basename(href)
                                # Clean up query params if present
                                if "?" in base_name:
                                    base_name = base_name.split("?")[0]

                                self.add_entry_to_results(
                                    url=href,
                                    dst_fn=base_name,
                                    data_type=f"{self.short_name}_subset",
                                    job_id=self.subset_job_id,
                                )
                        break

                    elif state in ["failed", "canceled"]:
                        logger.error(
                            f"Harmony Job {state}: {status.get('message', '')}"
                        )
                        break

                    elif state == "running":
                        logger.info(f"Harmony Job Running: {progress}%")
                        time.sleep(15)
                    else:
                        # queued, accepted, etc.
                        logger.info(f"Harmony Job Status: {state}")
                        time.sleep(10)

                except Exception as e:
                    logger.error(f"Harmony polling failed: {e}")
                    time.sleep(15)

    def run(self):
        """Run the EarthData fetch module."""

        if self.harmony_ping:
            if self.subset_job_id:
                status = self.harmony_ping_for_status(
                    self.subset_job_id, self.harmony_ping
                )
                if status:
                    logger.info(f"Ping Status: {status.get('status')}")
            return []

        if self.region is None:
            return []

        if not self.subset:
            self._run_cmr_search()
        else:
            self._run_harmony_subset()

        return self


# =============================================================================
# Shortcuts
# =============================================================================
@cli.cli_opts(help_text="NASA IceSat2 Data (ATL03/ATL08)")
class IceSat2(EarthData):
    """Shortcut for IceSat2 (ATL03/ATL08) data.

    If subset=True, this uses Harmony to spatially subset the HDF5 files
    server-side, saving significant bandwidth.
    """

    def __init__(
        self,
        short_name: str = "ATL03",
        subset: bool = False,
        version: str = "006",
        **kwargs,
    ):
        if short_name.upper().startswith("ATL"):
            short_name = short_name.upper()
        else:
            short_name = "ATL03"

        # Subset Collection IDs for Harmony
        if subset:
            collection_map = {
                "006": {
                    "ATL03": "C2596864127-NSIDC_CPRD",
                    "ATL08": "C2613553260-NSIDC_CPRD",
                },
                "007": {
                    "ATL03": "C3326974349-NSIDC_CPRD",
                    "ATL08": "C3565574177-NSIDC_CPRD",
                },
                # Add newer versions (007, etc) as needed
            }
            if version in collection_map and short_name in collection_map[version]:
                short_name = collection_map[version][short_name]

        # ## Default to One year ago -> Today
        # if not time_end:
        #     time_end = datetime.datetime.now().isoformat()
        # if not time_start:
        #     time_start = (datetime.datetime.now() - datetime.timedelta(days=365)).isoformat()

        super().__init__(
            short_name=short_name, subset=subset, version=version, **kwargs
        )


@cli.cli_opts(help_text="NASA SWOT Satellite Data")
class SWOT(EarthData):
    """Shortcut for SWOT (Surface Water and Ocean Topography) data."""

    def __init__(self, product: str = "L2_HR_Raster_2", **kwargs):
        super().__init__(short_name=f"SWOT_{product}*", **kwargs)


@cli.cli_opts(help_text="MUR SST (Global Sea Surface Temperature)")
class MUR_SST(EarthData):
    """Shortcut for MUR-SST Level 4 Global Sea Surface Temperature."""

    def __init__(self, **kwargs):
        super().__init__(short_name="MUR-JPL-L4-GLOB-v4.1", **kwargs)
