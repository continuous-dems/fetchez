#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.earthdata
~~~~~~~~~~~~~~~~~~~~~~~~~

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
import requests
from requests.auth import AuthBase
from tqdm.auto import tqdm
from typing import Dict, Optional

from fetchez import core
from fetchez.modules import FetchModule
from fetchez import spatial
from fetchez import cli

from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

CMR_SEARCH_URL = "https://cmr.earthdata.nasa.gov/search/granules.json?"
HARMONY_BASE_URL = "https://harmony.earthdata.nasa.gov"


class EarthdataAuth(AuthBase):
    """Custom Auth handler that mimics .netrc behavior across redirects."""

    def __init__(self, b64_credentials):
        self.b64_credentials = b64_credentials

    def __call__(self, r):
        # Only inject the Authorization header for NASA Earthdata domains
        if "earthdata.nasa.gov" in r.url.lower():
            r.headers["Authorization"] = f"Basic {self.b64_credentials}"
        return r


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
    harmony_ping="Harmony ping query, ['status', 'pause', 'resume', 'cancel', 'skip-preview']",
)
class EarthData(FetchModule):
    name = "earthdata"
    meta_category = "Generic"
    meta_desc = "NASA Earth Science Data via CMR & Harmony"
    meta_agency = "NASA"
    meta_tags = [
        "nasa",
        "cmr",
        "harmony",
        "satellite",
        "earth-science",
        "remote-sensing",
    ]
    meta_region = "Global"
    meta_resolution = "Varies"
    meta_license = "NASA Data and Information Policy (Open)"
    meta_urls = {
        "home": "https://earthdata.nasa.gov/",
        "search": "https://search.earthdata.nasa.gov/",
    }

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
        self.harmony_ping = harmony_ping  # see harmony_ping_for_status

        # URLs
        self._cmr_url = CMR_SEARCH_URL
        self._harmony_url = (
            f"{HARMONY_BASE_URL}/ogc-api-edr/1.1.0/collections/{short_name}/cube?"
        )

        # Authentication
        self.auth: Optional[EarthdataAuth] = None
        credentials = core.get_credentials(
            url="https://urs.earthdata.nasa.gov",
            authenticator_url="https://urs.earthdata.nasa.gov",
            env_user="EARTHDATA_USERNAME",
            env_pass="EARTHDATA_PASSWORD",
        )
        if credentials:
            self.headers = {
                # "Authorization": f"Basic {credentials}",
                "User-Agent": core.DEFAULT_USER_AGENT,
            }
            self.auth = EarthdataAuth(credentials)
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

        valid_requests = ["status", "pause", "resume", "cancel", "skip-preview"]
        base_url = f"{HARMONY_BASE_URL}/jobs/{job_id}"

        if ping_request in valid_requests[1:]:
            status_url = f"{base_url}/{ping_request}"
        else:
            status_url = base_url

        req = core.Fetch(status_url, headers=self.headers, auth=self.auth).fetch_req(
            timeout=10
        )
        if req and req.status_code == 200:
            return req.json()
        return None

    def harmony_make_request(self) -> Optional[Dict]:
        """Initiate a Harmony Subset Request."""

        if not self.wgs_region:
            return None

        w, e, s, n = self.wgs_region
        harmony_data = {
            "bbox": f"{w},{s},{e},{n}",
            "forceAsync": True,
        }

        start_t = self._format_date(self.time_start)
        end_t = self._format_date(self.time_end)

        if start_t != ".." or end_t != "..":
            harmony_data["datetime"] = f"{start_t}/{end_t}"

        logger.debug(f"Submitting Harmony Request for {self.short_name}...")

        req = core.Fetch(
            self._harmony_url, headers=self.headers, auth=self.auth
        ).fetch_req(params=harmony_data, timeout=30)

        if req and req.status_code in [200, 201, 202]:
            try:
                return req.json()
            except requests.exceptions.JSONDecodeError:
                logger.error(
                    "Harmony API returned HTML instead of JSON. You likely need to log into "
                    "https://urs.earthdata.nasa.gov and explicitly approve the 'Harmony' application "
                    "in your profile, or your authentication has been rejected."
                )
                logger.debug(f"Response snippet: {req.text[:500]}")
                return None

        logger.error(
            f"Harmony request failed: {req.status_code if req else 'No Response'}"
        )
        if req:
            logger.debug(req.text)
        return None

    def earthdata_set_config(self) -> Dict:
        """Configure CMR Search Parameters."""

        w, e, s, n = self.wgs_region

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
        logger.debug(f"Searching CMR for {self.short_name}...")

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
        logger.debug(f"CMR returned {len(entries)} potential granules.")

        # Prepare Shapely Polygon for precise filtering
        search_geom = None
        search_geom = spatial.region_to_shapely(self.wgs_region)

        for entry in entries:
            # Spatial Filtering (Refine BBox search)
            geom_valid = True

            # Check Polygon Intersection if Shapely available
            try:
                # CMR Polygons are list of lists: [['lat1 lon1 lat2 lon2 ...']]
                poly_str = entry["polygons"][0][0]
                coords = [float(x) for x in poly_str.split()]

                lats = coords[::2]
                lons = coords[1::2]
                points = list(zip(lons, lats, strict=True))

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

        logger.debug(f"Harmony ID: {self.subset_job_id}")
        if not self.subset_job_id:
            status = self.harmony_make_request()
            if status and "jobID" in status:
                self.subset_job_id = status["jobID"]
                logger.debug(f"Harmony Job Initiated: {self.subset_job_id}")
                logger.debug(
                    f"Harmony status url: {HARMONY_BASE_URL}/jobs/{self.subset_job_id}"
                )
            else:
                return

        if self.subset_job_id:
            logger.debug(f"Polling Harmony Job {self.subset_job_id}...")

            # States where Harmony is still working and polling should continue.
            _IN_PROGRESS_STATES = {
                "running",
                "paused",
                "previewing",
                "accepted",
                "queued",
            }

            with tqdm(total=100) as pbar:
                while True:
                    try:
                        status = self.harmony_ping_for_status(self.subset_job_id)
                        if not status:
                            time.sleep(10)
                            continue

                        progress = status.get("progress", 0)
                        state = status.get("status", "unknown")

                        if state == "successful":
                            pbar.update(100 - pbar.n)
                            logger.debug("Harmony Job Successful. Processing links...")
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

                        elif state == "complete_with_errors":
                            logger.warning(
                                f"Harmony Job completed with errors: {status.get('message', '')}. "
                                f"Partial results may be available."
                            )
                            break

                        elif state == "running":
                            pbar.update(float(progress) - pbar.n)
                            logger.debug(f"Harmony Job Running: {progress}%")
                            time.sleep(15)
                        elif state == "paused":
                            self.harmony_ping_for_status(self.subset_job_id, "resume")
                            time.sleep(10)
                        elif state == "previewing":
                            # A job over Harmony's preview threshold processes a
                            # small batch first and then pauses until told to go
                            # on. Skip the preview so it runs straight through.
                            # If the skip is refused the job still ends up
                            # paused, and the resume above picks it up.
                            logger.debug(
                                "Harmony Job is previewing; skipping the preview."
                            )
                            self.harmony_ping_for_status(
                                self.subset_job_id, "skip-preview"
                            )
                            time.sleep(10)
                        elif state in _IN_PROGRESS_STATES:
                            logger.debug(f"Harmony Job Status: {state}")
                            time.sleep(10)
                        else:
                            # Unrecognised terminal-or-unknown state — do not loop forever.
                            logger.warning(
                                f"Harmony Job returned unrecognised status '{state}'; "
                                f"stopping poll."
                            )
                            break

                    except Exception as e:
                        logger.exception(f"Harmony polling failed: {e}")
                        time.sleep(15)

    def run(self):
        """Run the EarthData fetch module."""

        if self.harmony_ping:
            if self.subset_job_id:
                status = self.harmony_ping_for_status(
                    self.subset_job_id, self.harmony_ping
                )
                if status:
                    logger.debug(f"Ping Status: {status.get('status')}")
            return []

        if self.wgs_region is None:
            return []

        if not self.subset:
            self._run_cmr_search()
        else:
            self._run_harmony_subset()

        return self


# =============================================================================
# Shortcuts
# =============================================================================
@cli.cli_opts(
    help_text="NASA IceSat2 Data (ATL03/ATL08)",
    short_name="Dataset Short Name (e.g. ATL03, ATL08, MUR-JPL-L4-GLOB-v4.1)",
    version="Dataset Version (e.g. 007)",
    subset="Use Harmony API for subsetting (if supported)",
)
class IceSat2(EarthData):
    """Shortcut for IceSat2 (ATL03/ATL08) data.

    If subset=True, this uses Harmony to spatially subset the HDF5 files
    server-side, saving significant bandwidth.
    """

    name = "icesat2"

    def __init__(
        self,
        short_name: str = "ATL03",
        subset: bool = False,
        version: str = "007",
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

    name = "swot"

    def __init__(self, product: str = "L2_HR_Raster_2", **kwargs):
        super().__init__(short_name=f"SWOT_{product}*", **kwargs)


@cli.cli_opts(help_text="MUR SST (Global Sea Surface Temperature)")
class MUR_SST(EarthData):
    """Shortcut for MUR-SST Level 4 Global Sea Surface Temperature."""

    name = "mur_sst"

    def __init__(self, **kwargs):
        super().__init__(short_name="MUR-JPL-L4-GLOB-v4.1", **kwargs)
