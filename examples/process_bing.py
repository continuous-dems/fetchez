#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
process_bing.py
~~~~~~~~~~~~~~~

A standalone workflow script that uses 'fetchez' to download
Microsoft Bing Building Footprints and merges them into a single
GeoPackage (GPKG) using GDAL/OGR.

Usage:
    python process_bing.py -R -105.5/-104.5/39.5/40.5 -o boulder_buildings.gpkg

Dependencies:
    pip install fetchez
    (GDAL is required for geometry processing)
"""

import os
import sys
import argparse
import gzip
import shutil
import logging

try:
    from osgeo import ogr, osr

    HAS_GDAL = True
except ImportError:
    print("ERROR: This script requires GDAL (osgeo).")
    sys.exit(1)

# Import Fetchez
from fetchez import core
from fetchez import registry
from fetchez import spatial

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bing_proc")


class BingProcessor:
    def __init__(self, region, out_fn, threads=5, keep_raw=False):
        self.region = region
        self.out_fn = out_fn
        self.threads = threads
        self.keep_raw = keep_raw

        # Determine cache dir
        self.cache_dir = os.path.join(os.getcwd(), "bing_cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def fetch(self):
        """Use fetchez to discover and download data."""

        logger.info("Initializing Fetchez...")

        # Load the Bing module dynamically from registry
        # This ensures we are using the installed fetchez module
        BingModule = registry.FetchezRegistry.load_module("bing")

        if not BingModule:
            logger.error("Could not load 'bing' module from fetchez. Is it registered?")
            sys.exit(1)

        # Initialize and Run the Module
        # We pass the cache directory so files land there
        fetcher = BingModule(
            src_region=self.region, outdir=os.path.dirname(self.cache_dir)
        )
        self.cache_dir = os.path.join(self.cache_dir, fetcher._outdir)

        logger.info("Querying Microsoft API for tiles...")
        fetcher.run()

        if not fetcher.results:
            logger.warning("No building footprint tiles found for this region.")
            return []

        # Run the Parallel Downloader
        logger.info(f"Downloading {len(fetcher.results)} tiles...")
        core.run_fetchez([fetcher], threads=self.threads)

        return fetcher.results

    def process(self, results):
        """Merge downloaded GeoJSONs into one GeoPackage."""

        if not results:
            return

        logger.info(f"Processing into {self.out_fn}...")

        # Create the Output Layer (GPKG)
        driver = ogr.GetDriverByName("GPKG")
        if os.path.exists(self.out_fn):
            driver.DeleteDataSource(self.out_fn)

        ds_out = driver.CreateDataSource(self.out_fn)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)  # Microsoft data is WGS84

        layer_out = ds_out.CreateLayer("buildings", srs, ogr.wkbPolygon)

        # We'll create the schema based on the first feature we find
        schema_defined = False

        total_feats = 0

        for entry in results:
            # local_path = os.path.join(self.cache_dir, entry['dst_fn'])
            local_path = entry["dst_fn"]

            if not os.path.exists(local_path):
                logger.warning(f"File missing: {local_path}")
                continue

            # Unzip (.gz -> .geojson)
            json_path = local_path.replace(".gz", "")
            try:
                with gzip.open(local_path, "rb") as f_in:
                    with open(json_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            except Exception as e:
                logger.error(f"Failed to unzip {local_path}: {e}")
                continue

            # Open GeoJSON
            ds_in = ogr.Open(json_path)
            if not ds_in:
                continue

            layer_in = ds_in.GetLayer()

            # Define Schema (Once)
            if not schema_defined:
                layer_defn = layer_in.GetLayerDefn()
                for i in range(layer_defn.GetFieldCount()):
                    field_defn = layer_defn.GetFieldDefn(i)
                    layer_out.CreateField(field_defn)
                schema_defined = True

            # Copy Features
            # Optional: Apply Spatial Filter again to clip tightly to region
            # (The tiles are loose QuadKeys, so they might overshoot the bbox)
            w, e, s, n = self.region
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(w, s)
            ring.AddPoint(w, n)
            ring.AddPoint(e, n)
            ring.AddPoint(e, s)
            ring.AddPoint(w, s)
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)
            layer_in.SetSpatialFilter(poly)

            layer_defn = layer_out.GetLayerDefn()
            for feat in layer_in:
                # create new feature
                out_feat = ogr.Feature(layer_defn)
                out_feat.SetGeometry(feat.GetGeometryRef())

                # copy attrs
                for i in range(layer_defn.GetFieldCount()):
                    out_feat.SetField(i, feat.GetField(i))

                layer_out.CreateFeature(out_feat)
                out_feat = None
                total_feats += 1

            ds_in = None  # Close input

            # Cleanup
            if not self.keep_raw:
                if os.path.exists(json_path):
                    os.remove(json_path)
                if os.path.exists(local_path):
                    os.remove(local_path)

        logger.info(f"Finished. Wrote {total_feats} buildings to {self.out_fn}")
        ds_out = None  # Close output


def main():
    parser = argparse.ArgumentParser(
        description="Download and Merge Bing Building Footprints via Fetchez"
    )
    parser.add_argument(
        "-R",
        "--region",
        required=True,
        help="Region: west/east/south/north (e.g., -105.3/-105.2/40.0/40.1)",
    )
    parser.add_argument(
        "-o", "--output", default="buildings.gpkg", help="Output GeoPackage filename"
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=4, help="Number of download threads"
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Do not delete the downloaded GeoJSON tiles",
    )

    args = parser.parse_args()

    # Parse Region
    try:
        # returns a list of Region objects
        regions = spatial.parse_cli_region([args.region])
        region = regions[0]
    except Exception as e:
        print(f"Invalid Region: {e}")
        sys.exit(1)

    processor = BingProcessor(
        region=region, out_fn=args.output, threads=args.threads, keep_raw=args.keep_raw
    )

    # Run Workflow
    results = processor.fetch()
    processor.process(results)


if __name__ == "__main__":
    main()
