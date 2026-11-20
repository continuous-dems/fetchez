#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.copernicus_marine
~~~~~~~~~~~~~~~~~~~~

Fetch data from the copernicus marine store, using
the copernincusmarine api.

:copyright: (c) 2025 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import filelock
from pathlib import Path
from fetchez.modules import FetchModule
from fetchez.core import get_raw_credentials, FetchCancelled
from fetchez import cli

try:
    import copernicusmarine

    HAS_COPMARINE = True
except ImportError:
    HAS_COPMARINE = False

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Copernicus Marine SDB Fetcher",
    dataset_id="The Copernicus Marine dataset ID (e.g., cmems_obs-mob_glo_bathy_sdb_multi_15m_pt15s)",
    username="Copernicus Marine Username (or set in netrc)",
    password="Copernicus Marine Password (or set in netrc)",
)
class CopernicusMarineSDB(FetchModule):
    """Fetches Satellite Derived Bathymetry from the Copernicus Marine Service."""

    name = "copernicus_marine"
    meta_category = "Bathymetry"
    meta_agency = "ESA"
    meta_region = "Global"
    meta_resolution = "Varies"
    meta_license = "TBD"

    meta_desc = "Copernicus Marine data discovery and native subsetting"
    meta_tags = [
        "copernicus",
        "marine",
        "bathymetry",
        "oceanography",
        "subset",
        "netcdf",
    ]
    meta_provides = ["raster", "netcdf"]

    def __init__(self, dataset_id=None, username=None, password=None, **kwargs):
        super().__init__(**kwargs)
        self.dataset_id = (
            dataset_id or "cmems_obs-sdb_glo_phy_comp_my_100m-l4-s2_static"
        )

        self.username = username
        self.password = password

    def _output_filename(self):
        out_fn = f"{self.dataset_id}_{self.wgs_region.xmin}_{self.wgs_region.ymin}_{self.wgs_region.xmax}_{self.wgs_region.ymax}.nc"
        out_path = Path(self._outdir) / out_fn

        return out_path

    def run(self):
        self.add_entry_to_results(
            url=f"copernicusmarine://{self.dataset_id}",
            dst_fn=self._output_filename(),
            data_type="raster",
            acquisition={
                "operation": "subset",
                "dataset_id": self.dataset_id,
                "bbox": [
                    self.wgs_region.xmin,
                    self.wgs_region.ymin,
                    self.wgs_region.xmax,
                    self.wgs_region.ymax,
                ],
            },
        )
        return self

    def fetch_entry(self, entry, check_size=True, retries=5, verbose=True):
        if not HAS_COPMARINE:
            raise ImportError(
                "Copernicus Marine requires: pip install copernicusmarine"
            )

        if self.context is not None and self.context.cancelled:
            raise FetchCancelled("Copernicus Marine acquisition cancelled")

        spec = entry["acquisition"]
        bbox = spec["bbox"]

        output = Path(entry["dst_fn"])
        output.parent.mkdir(parents=True, exist_ok=True)

        username = self.username
        password = self.password

        if not username or not password:
            netrc_user, netrc_password = get_raw_credentials(
                "https://data.marine.copernicus.eu", "https://data.marine.copernicus.eu"
            )
            username = username or netrc_user
            password = password or netrc_password

        # Let the Copernicus client use its own supported auth
        # configuration if credentials weren't explicitly provided.
        auth_kwargs = {}
        if username and password:
            auth_kwargs = {
                "username": username,
                "password": password,
            }

        with filelock.FileLock(f"{output}.lock", timeout=3600):
            if output.is_file() and output.stat().st_size > 0:
                entry["status"] = 0
                return 0

            if self.context is not None and self.context.cancelled:
                raise FetchCancelled("Copernicus Marine acquisition cancelled")

            try:
                copernicusmarine.subset(
                    dataset_id=spec["dataset_id"],
                    minimum_longitude=bbox[0],
                    minimum_latitude=bbox[1],
                    maximum_longitude=bbox[2],
                    maximum_latitude=bbox[3],
                    output_directory=str(output.parent),
                    output_filename=output.name,
                    skip_existing=True,
                    **auth_kwargs,
                )

                if not output.is_file() or (check_size and output.stat().st_size == 0):
                    raise RuntimeError(
                        f"Copernicus Marine produced no valid output: {output}"
                    )

            except FetchCancelled:
                raise
            except Exception:
                logger.exception(
                    "Copernicus Marine acquisition failed for %s",
                    spec["dataset_id"],
                )
                raise

        entry["status"] = 0
        return 0
