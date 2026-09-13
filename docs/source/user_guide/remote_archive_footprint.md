# Remote archive footprints

`remote_archive_footprint` reads polygon boundaries from a shapefile inside a
remote ZIP and attaches them to each Fetchez entry before the archive is
downloaded. It uses HTTP range reads to retrieve the ZIP directory and the
selected shapefile components, leaving unrelated files in the archive unread.
The server must support byte ranges. No additional dependencies are required.

The hook accepts direct HTTP ZIP URLs from any module. It does not inspect
raster values, interpret project names, select newer surveys, or apply TNM
resolution rules. This first version supports ZIP shapefiles; standalone
GeoPackages such as WESM are a separate reader/integration task.

Use the hook on archives known to contain footprint polygons. For example:

```bash
fetchez run --global-hook list-only -R -124.5/-124.0/41.5/44.0 \
  tnm --datasets 1_9as --hook remote_archive_footprint
```

If an archive contains multiple shapefiles, select one by its exact member
path using `layer`, for example `layer=metadata/footprint.shp`. Paths are
case-sensitive. Without a selection, exactly one shapefile must be present.
Use `fields=project/year` to retain specific attribute columns, or omit
`fields` to keep all columns. Python callers can also pass a list of field
names. Field names are preserved without TNM-specific renaming.

The hook sets:

- `geometry`: the union of the selected layer's polygons, as a Shapely geometry
  in WGS84 longitude/latitude. It replaces any previous entry geometry and can
  be consumed by `spatial_cull`.
- `footprint_features`: individual records containing `fid`, WGS84 `geometry`
  as WKT, and `properties` with the selected attributes. These records preserve
  feature boundaries even though the entry-level geometry is combined.
- `footprint_layer`: the selected ZIP member path. Together with the unchanged
  entry `url` and each `fid`, this identifies the source of the extracted data.

Polygon holes are preserved as supplied. Unlike a raster-extent hook, this
reader does not invent a perimeter or fill holes in published vector geometry.
It transforms existing vertices; it does not densify sparse curved edges.
It neither clips to an ROI nor turns individual features into duplicate file
downloads. Downstream code must interpret coverage and provenance semantics.

Missing layers, required shapefile components, selected fields, CRS, empty
layers, and invalid/non-polygon geometry raise errors. Extents crossing WGS84
longitude limits are rejected rather than returned as misleading polygons.
The hook does not change the pipeline's normal error-handling policy.

Only selected shapefile components are written to a temporary directory, using
fixed local filenames. ZIP member paths are never used as extraction paths.
Temporary files and HTTP responses are closed after reading, including errors.
