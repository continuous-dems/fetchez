#!/usr/bin/env python

"""
fetchez.modules.bluetopo
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA BlueTopo bathymetric data directly from AWS S3.

BlueTopo is a compilation of the nation's best available bathymetric data,
created as part of the Office of Coast Survey's National Bathymetric Source project.

:copyright: (c) 2010 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.client import Config

    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

from pyogrio.raw import read

from fetchez import cli, core
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

BLUETOPO_BUCKET = "noaa-ocs-nationalbathymetry-pds"
BLUETOPO_PREFIX = "BlueTopo"


@cli.cli_opts(
    help_text="NOAA BlueTopo (National Bathymetric Source)",
    keep_index="Retain the bluetopo source index",
)
class BlueTopo(FetchModule):
    name = "bluetopo"
    meta_category = "Bathymetry"
    meta_desc = "NOAA BlueTopo (National Bathymetric Source) via AWS S3"
    meta_agency = "NOAA OCS"
    meta_tags = ["bathymetry", "noaa", "bluetopo", "nbs", "ocean", "elevation"]
    meta_region = "USA"
    meta_resolution = "Variable"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://nauticalcharts.noaa.gov/data/bluetopo.html"}

    """NOAA BlueTopo Bathymetry (AWS S3)",

    **Dependencies:**
    - `pyogrio`: Required to parse the gpkg index (`pip install pyogrio`)
    - `boto3`: Required to access the amazon s3 bucket
    """

    def __init__(
        self,
        want_interpolation: bool = False,
        unc_weights: bool = False,
        keep_index: bool = False,
        **kwargs,
    ):
        super().__init__(name="bluetopo", **kwargs)
        self.want_interpolation = want_interpolation
        self.unc_weights = unc_weights
        self.keep_index = keep_index

        self._bluetopo_index_url = None
        self._bluetopo_index_fn = None

    def _get_s3_client(self):
        """Return an anonymous S3 client."""
        return boto3.client("s3", config=Config(signature_version=UNSIGNED))

    def _get_index_url(self, s3_client) -> str | None:
        """Dynamically find the Tile Scheme index file URL from S3."""
        try:
            r = s3_client.list_objects(
                Bucket=BLUETOPO_BUCKET,
                Prefix=f"{BLUETOPO_PREFIX}/_BlueTopo_Tile_Scheme",
            )
            if "Contents" in r and len(r["Contents"]) > 0:
                key = r["Contents"][0]["Key"]
                return f"https://{BLUETOPO_BUCKET}.s3.amazonaws.com/{key}"
        except Exception as e:
            logger.error(f"Error finding BlueTopo index on S3: {e}")
        return None

    def run(self):
        """Run the BlueTopo fetch module."""

        if not HAS_BOTO:
            logger.error('This module requires "boto3". Please install it to proceed.')
            return self

        if self.wgs_region is None:
            return self

        s3 = self._get_s3_client()

        if self._bluetopo_index_url is None:
            logger.info("Locating BlueTopo Tile Scheme on S3...")
            self._bluetopo_index_url = self._get_index_url(s3)

        if not self._bluetopo_index_url:
            logger.error("Could not locate BlueTopo tile index.")
            return self

        self._bluetopo_index_fn = (
            Path(self._outdir) / Path(self._bluetopo_index_url).name
        )
        try:
            if not self._bluetopo_index_fn.exists():
                logger.info(f"Downloading index: {self._bluetopo_index_fn.name}...")
                status = core.Fetch(self._bluetopo_index_url).fetch_file(
                    self._bluetopo_index_fn
                )
                if status != 0:
                    raise OSError("Failed to download BlueTopo index.")

            logger.info("Querying tile index with pyogrio...")

            w, e, s, n = self.wgs_region
            bbox = (w, s, e, n)

            try:
                meta, fids, geometry_wkb, fields = read(
                    self._bluetopo_index_fn, bbox=bbox, columns=["tile"]
                )

                feature_count = len(geometry_wkb)

                if feature_count == 0:
                    logger.info("No BlueTopo tiles found in this region.")
                    return self

                logger.info(f"Found {feature_count} intersecting tiles.")

                for tile_name in fields[0]:
                    if not tile_name:
                        continue

                    try:
                        r = s3.list_objects(
                            Bucket=BLUETOPO_BUCKET,
                            Prefix=f"{BLUETOPO_PREFIX}/{tile_name}",
                        )
                        if "Contents" in r:
                            for obj in r["Contents"]:
                                key = obj["Key"]
                                if key.endswith(".tiff"):
                                    data_link = f"https://{BLUETOPO_BUCKET}.s3.amazonaws.com/{key}"
                                    self.add_entry_to_results(
                                        url=data_link,
                                        dst_fn=Path(key).name,
                                        data_type="bluetopo_tiff",
                                        agency="NOAA OCS",
                                        title=tile_name,
                                        license="Public Domain",
                                    )
                    except Exception as e:
                        logger.warning(
                            f"Failed to resolve file for tile {tile_name}: {e}"
                        )

            except Exception as e:
                logger.error(f"Error reading BlueTopo index: {e}")

        except Exception as e:
            logger.error(f"BlueTopo Run Error: {e}")

        finally:
            if not self.keep_index and self._bluetopo_index_fn:
                self._bluetopo_index_fn.unlink(missing_ok=True)

        return self
