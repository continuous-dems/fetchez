#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
hook_reproject.py
~~~~~~~~~~~~~~~~~

A Fetchez User Hook to automatically reproject downloaded raster data
using GDAL.

Installation:
  1. Copy this file to ~/.fetchez/hooks/reproject.py
  2. Install GDAL: `conda install gdal` or `pip install gdal`

Usage:
  fetchez copernicus --hook reproject:crs=EPSG:3857

Description:
  This hook inspects the 'entry' dictionary for a 'crs' key (which indicates
  the source projection). If found, it uses that as the source srs in GDAL to warp the file to the
  target CRS.
"""

import os
import logging
from fetchez.hooks import FetchHook

# Soft import so the hook doesn't crash fetchez if GDAL isn't installed
try:
    from osgeo import gdal
    HAS_GDAL = True
except ImportError:
    HAS_GDAL = False

logger = logging.getLogger(__name__)

class Reproject(FetchHook):
    """Reproject rasters using GDAL."""

    name = "reproject"
    desc = "Warp rasters to a target CRS. Usage: --hook reproject:crs=EPSG:3857"
    stage = 'file'  # Runs immediately after download (in the thread)

    def __init__(self, crs='EPSG:3857', suffix='_warped', **kwargs):
        """
        Args:
            crs (str): Target CRS (e.g., 'EPSG:4326', 'EPSG:3857').
            suffix (str): Suffix to append to the reprojected filename.
        """

        super().__init__(**kwargs)
        self.target_crs = crs
        self.suffix = suffix


    def run(self, entries):
        # If GDAL is missing, log a warning once and pass data through untouched
        if not HAS_GDAL:
            logger.warning("Hook 'reproject' skipped: GDAL not installed.")
            return entries

        processed_entries = []

        for mod, entry in entries:
            url = entry.get('url')
            src_path = entry.get('dst_fn')
            status = entry.get('status')
            source_crs = entry.get('crs') # context check (this may have been added by the module)

            # Skip if download failed, source CRS is unknown, or we already matched the target
            if status != 0 or not source_crs or source_crs == self.target_crs:
                processed_entries.append(entry)
                continue

            # Skip if it doesn't look like a raster (simple extension check)
            # We could also check gdal.Open(src_path) inside a try block
            valid_exts = ['.tif', '.tiff', '.img', '.nc', '.gtiff']
            _, ext = os.path.splitext(src_path)
            if ext.lower() not in valid_exts:
                processed_entries.append((mod, entry))
                continue

            # Prepare Output Path
            # /path/to/data.tif -> /path/to/data_warped.tif
            base, ext = os.path.splitext(src_path)
            dst_path = f"{base}{self.suffix}{ext}"

            try:
                # Perform Reprojection
                # We use gdal.Warp
                logger.info(f"Reprojecting {os.path.basename(src_path)} to {self.target_crs}...")

                warp_opts = gdal.WarpOptions(
                    dstSRS=self.target_crs,
                    srcSRS=source_crs,
                    format='GTiff'
                )

                # Run the warp
                ds = gdal.Warp(dst_path, src_path, options=warp_opts)
                ds = None # Flush to disk

                # We return the NEW path so subsequent hooks (like --pipe-path) use the warped file
                processed_entries.append({
                    'url': url,
                    'dst_fn': dst_path,
                    'data_type': 'grid_warped',
                    'status': 0,
                    'crs': self.target_crs # Update context for downstream hooks
                })

            except Exception as e:
                logger.error(f"Reprojection failed for {src_path}: {e}")
                # On failure, pass the original file through
                processed_entries.append((mod, entry))

        return processed_entries
