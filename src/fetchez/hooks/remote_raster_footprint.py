"""Attach remote raster extents to manifest entries before downloading."""

import itertools

import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

from fetchez.core import gdal_vsi_path
from fetchez.hooks import FetchHook


class RemoteRasterFootprintHook(FetchHook):
    """Read raster edges, including NoData areas, as WGS84 entry geometry.

    This replaces any existing geometry with the raster extent. It does not
    identify valid pixels or published survey coverage, clip to an ROI, or cull
    entries. Requires the optional ``fetchez[raster]`` dependency.
    """

    name = "remote_raster_footprint"
    meta_stage = "manifest"
    meta_desc = "Set entry geometry from a remote raster's outer extent."

    def run(self, entries):
        if not entries:
            return entries

        # Keep rasterio optional for discovery and unrelated hooks.
        import rasterio

        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="TRUE"):
            for _, entry in entries:
                with rasterio.open(gdal_vsi_path(entry["url"])) as source:
                    if source.crs is None:
                        raise ValueError(f"Raster has no CRS: {entry['url']}")
                    crs = CRS(source.crs)
                    if crs.is_compound:
                        crs = crs.sub_crs_list[0]
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
                    # Preserve curved edges when projecting, at pixel spacing.
                    footprint = shapely.segmentize(footprint, min(source.res))
                    footprint = transform(
                        Transformer.from_crs(crs, 4326, always_xy=True).transform,
                        footprint,
                    )
                    coords = list(footprint.exterior.coords)
                    if any(
                        abs(a[0] - b[0]) > 180 for a, b in itertools.pairwise(coords)
                    ) or any(abs(x) > 180 or abs(y) > 90 for x, y in coords):
                        raise ValueError(
                            f"Raster extent crosses WGS84 limits: {entry['url']}"
                        )
                    if (
                        footprint.is_empty
                        or not footprint.is_valid
                        or footprint.area <= 0
                    ):
                        raise ValueError(f"Invalid raster extent: {entry['url']}")
                entry["geometry"] = footprint
        return entries
