#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
process_osm_coastline.py
~~~~~~~~~~~~~~~~~~~~~~~~

Recipe: Fetch raw OSM Coastline data and process it into clean Land/Water polygons.

This script demonstrates:
 - Using `fetchez` to download raw OSM XML chunks.
 - Using `osgeo.ogr` (GDAL) to union lines and polygonize them.
 - Handling the logic of "Land on left, Water on right".

Dependencies:
    pip install fetchez gdal
"""

import os
import sys
import argparse
from fetchez import core, registry
from osgeo import ogr, osr


def fetch_osm(region, out_dir):
    """Use fetchez to get the raw .osm files."""
    
    print("1. Fetching raw OSM data...")
    
    OSM = registry.FetchezRegistry.load_module('osm')
    fetcher = OSM(
        src_region=region,
        query='coastline',
        chunk_size=0.5, # Small chunks to ensure high-res capture
        outdir=out_dir
    )
    fetcher.run()
    core.run_fetchez([fetcher])
    
    # Return list of downloaded files
    return [os.path.join(out_dir, r['dst_fn']) for r in fetcher.results]


def process_to_polygons(osm_files, output_gpkg, region):
    """Convert OSM lines to Land/Water polygons.
    
    This is a simplified version of the algorithm:
    1. Merge all OSM lines.
    2. Create a box for the region.
    3. Cut the box with the lines.
    4. Determine which pieces are land vs water.
    """
    
    print(f"2. Processing {len(osm_files)} files into polygons...")
    
    # Setup Driver
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(output_gpkg):
        driver.DeleteDataSource(output_gpkg)
    ds_out = driver.CreateDataSource(output_gpkg)
    layer_out = ds_out.CreateLayer("coastline", geom_type=ogr.wkbPolygon)
    layer_out.CreateField(ogr.FieldDefn("type", ogr.OFTString)) # 'Land' or 'Water'
    
    # Collect all lines
    multi_line = ogr.Geometry(ogr.wkbMultiLineString)
    
    for fn in osm_files:
        ds = ogr.Open(fn)
        if not ds: continue
        layer = ds.GetLayer() # usually 'lines' in OSM driver
        
        for feat in layer:
            geom = feat.GetGeometryRef()
            if geom:
                # Add to our collector
                if geom.GetGeometryType() == ogr.wkbLineString:
                    multi_line.AddGeometry(geom)
                elif geom.GetGeometryType() == ogr.wkbMultiLineString:
                    for i in range(geom.GetGeometryCount()):
                        multi_line.AddGeometry(geom.GetGeometryRef(i))
    
    # Union lines to fix gaps
    # Note: A small buffer can help stitch imperfect topology
    lines_merged = multi_line.UnionCascaded()
    
    # Create Region Box
    w, e, s, n = region
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(w, s)
    ring.AddPoint(e, s)
    ring.AddPoint(e, n)
    ring.AddPoint(w, n)
    ring.AddPoint(w, s)
    box = ogr.Geometry(ogr.wkbPolygon)
    box.AddGeometry(ring)
    
    # Polygonize (Difference)
    # Splitting the box by the lines creates the land/water chunks
    # Note: This requires the lines to fully cross the box or form closed loops.
    # A robust implementation (like osmCoastlinePolygonizer) checks line direction.
    # For this example, we assume closed loops or use a simple heuristic.
    
    try:
        # Buffer lines slightly to turn them into splitting polygons
        splitter = lines_merged.Buffer(0.000001) 
        result = box.Difference(splitter)
        
        # Save
        # In a real scenario, you'd check 'Point in Polygon' against a known point
        # to classify Land vs Water. Here we just save the geometry.
        
        feat_def = layer_out.GetLayerDefn()
        
        if result.GetGeometryType() == ogr.wkbPolygon:
            f = ogr.Feature(feat_def)
            f.SetGeometry(result)
            f.SetField("type", "Unknown")
            layer_out.CreateFeature(f)
        elif result.GetGeometryType() == ogr.wkbMultiPolygon:
            for i in range(result.GetGeometryCount()):
                poly = result.GetGeometryRef(i)
                f = ogr.Feature(feat_def)
                f.SetGeometry(poly)
                f.SetField("type", "Unknown")
                layer_out.CreateFeature(f)
                
        print(f"✅ Created {output_gpkg}")
        
    except Exception as e:
        print(f"Error during topology operation: {e}")

        
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', required=True, nargs=4, type=float, help="w e s n")
    parser.add_argument('--out', default='coast.gpkg')
    args = parser.parse_args()
    
    # Temp dir for XMLs
    cache_dir = 'osm_cache'
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    
    files = fetch_osm(args.region, cache_dir)
    process_to_polygons(files, args.out, args.region)

    
if __name__ == '__main__':
    main()
