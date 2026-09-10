"""Read the published raster extent for projected TNM elevation products."""

import time

import requests
import rasterio
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

from fetchez import core, spatial


def add_source_coverage(entries, region):
    """Use raster edges, never valid-data holes, as the source footprint."""
    roi = spatial.region_to_shapely(region)
    selected = []
    with requests.Session() as session:
        for entry in entries:
            for attempt in range(3):
                try:
                    with core.HttpFile(entry["url"], session=session) as remote:
                        with rasterio.open(remote) as source:
                            if source.crs is None:
                                raise RuntimeError("TNM raster has no source CRS")
                            crs = CRS(source.crs)
                            if crs.is_compound:
                                crs = crs.sub_crs_list[0]
                            # Densify at pixel spacing before projecting the perimeter.
                            corners = [
                                source.transform * point
                                for point in (
                                    (0, 0),
                                    (source.width, 0),
                                    (source.width, source.height),
                                    (0, source.height),
                                )
                            ]
                            footprint = shapely.Polygon(corners)
                            footprint = shapely.segmentize(footprint, min(source.res))
                            footprint = transform(
                                Transformer.from_crs(
                                    crs, 4326, always_xy=True
                                ).transform,
                                footprint,
                            )
                            entry["tnm_raster_crs"] = source.crs.to_wkt()
                    break
                except (requests.RequestException, OSError):
                    if attempt == 2:
                        raise
                    time.sleep(2**attempt)
            coverage = footprint.intersection(roi)
            if coverage.is_empty or coverage.area == 0:
                continue
            entry["tnm_source_coverage"] = [
                {
                    "geometry": shapely.to_wkt(coverage, rounding_precision=-1),
                    "source": entry["url"],
                }
            ]
            selected.append(entry)
    return selected
