#!/usr/bin/env python

"""
fetchez.modules.sentinel2
~~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Sentinel-2 Imagery via sentinelsat.
Includes Smart-Fallback bridging for Legacy SciHub and Modern CDSE endpoints.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from fetchez import cli, core
from fetchez.modules import FetchModule

try:
    from sentinelsat import SentinelAPI

    HAS_SENTINEL = True
except ImportError:
    HAS_SENTINEL = False

logger = logging.getLogger(__name__)

# --- API Endpoints ---
# Modern CDSE (Requires sentinelsat >= 1.2.1)
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
# Legacy SciHub Facade (Works on older sentinelsat versions)
LEGACY_API_URL = "https://apihub.copernicus.eu/apihub"


@cli.cli_opts(
    help_text="Copernicus Sentinel-2 Imagery",
    start_date="Start Date (YYYYMMDD). Default: 30 days ago.",
    end_date="End Date (YYYYMMDD). Default: Today.",
    cloud_cover="Max Cloud Cover % (0-100). Default: 20",
)
class Sentinel2(FetchModule):
    name = "sentinel2"
    meta_category = "Imagery"
    meta_desc = "Copernicus Sentinel-2 (Optical Imagery)"
    meta_agency = "ESA"
    meta_tags = ["sentinel", "satellite", "imagery", "copernicus", "esa", "optical"]
    meta_region = "Global"
    meta_resolution = "10m / 20m / 60m"
    meta_license = "Copernicus Open Access"
    meta_urls = {
        "home": "https://dataspace.copernicus.eu/",
        "auth": "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/account/",
    }

    """Fetch Sentinel-2 optical satellite imagery."""

    def __init__(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        cloud_cover: int = 20,
        **kwargs,
    ):
        super().__init__(name="sentinel2", **kwargs)
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = int(cloud_cover)

    def run(self):
        if self.wgs_region is None:
            logger.error("A region is required for Sentinel-2.")
            return self

        if not HAS_SENTINEL:
            logger.error(
                "This module requires 'sentinelsat'. Install via: pip install sentinelsat"
            )
            return self

        username, password = core.get_userpass(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        )
        if not username:
            username, password = core.get_userpass("dataspace.copernicus.eu")

        if not username or not password:
            logger.error("No Sentinel-2 credentials found in ~/.netrc")
            return self

        if not self.start_date:
            self.start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        else:
            self.start_date = self.start_date.replace("-", "")

        if not self.end_date:
            self.end_date = datetime.now().strftime("%Y%m%d")
        else:
            self.end_date = self.end_date.replace("-", "")

        w, e, s, n = self.wgs_region
        footprint = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

        products = None
        api = None

        try:
            # Attempt Modern CDSE OData API
            api = SentinelAPI(username, password, CDSE_ODATA_URL)
            products = api.query(
                footprint,
                date=(self.start_date, self.end_date),
                platformname="Sentinel-2",
                cloudcoverpercentage=(0, self.cloud_cover),
            )
            logger.info("Successfully connected to modern CDSE endpoint.")
        except Exception as e:
            logger.debug(
                f"Modern CDSE query failed (likely older sentinelsat version): {e}"
            )

        if not products:
            try:
                # Fallback to Legacy
                logger.info("Falling back to Legacy Copernicus endpoint...")
                api = SentinelAPI(username, password, LEGACY_API_URL, timeout=120)
                products = api.query(
                    footprint,
                    date=(self.start_date, self.end_date),
                    platformname="Sentinel-2",
                    cloudcoverpercentage=(0, self.cloud_cover),
                )
            except Exception as e:
                logger.error(f"Sentinel-2 Query Error: {e}")
                return self

        if not products:
            logger.warning("No Sentinel-2 scenes found matching criteria.")
            return self

        logger.info(f"Found {len(products)} scenes. Downloading via sentinelsat...")

        out_dir = getattr(self, "_outdir", Path.cwd())
        if out_dir and not Path(out_dir).exists():
            Path(out_dir).mkdir(parents=True, exist_ok=True)

        try:
            downloaded, triggered, failed = api.download_all(
                products, directory_path=out_dir
            )

            for uuid, info in downloaded.items():
                self.add_entry_to_results(
                    url="local",
                    dst_fn=info["path"],
                    data_type="sentinel2",
                    status=0,
                    title=info.get("title", uuid),
                )

            if failed:
                logger.warning(
                    f"Sentinelsat failed to download {len(failed)} products."
                )

        except Exception as e:
            logger.error(f"Sentinel-2 Download Error: {e}")

        return self
