# Remote raster footprints

The `remote_raster_footprint` manifest hook reads georeferencing from remote
rasters before downloading them and sets each entry's `geometry` to the raster's
outer perimeter in WGS84 longitude/latitude. It works with any module returning
HTTP raster URLs; it has no TNM-specific fields or product rules.

Install the optional raster dependency:

```bash
pip install 'fetchez[raster]'
```

For example, inspect TNM raster extents without downloading the full datasets:

```bash
fetchez run --global-hook list-only -R -124.5/-124.0/41.5/44.0 \
  tnm --datasets 1_as --hook remote_raster_footprint
```

The hook replaces existing entry geometry deliberately. Apply it only to direct
raster endpoints whose outer extent is the geometry you want. It preserves
rotated edges and densifies the perimeter at pixel spacing before reprojection.
This includes interior NoData areas: the result is not a valid-pixel mask or an
authoritative survey/project boundary. Longitude-wrapping extents at the
antimeridian are rejected by this hook rather than returned as misleading
coverage polygons. Splitting those extents requires additional handling.

The hook does not clip or remove entries. A following `spatial_cull` hook can
use the generated geometry to remove covered entries; resolution precedence,
partial coverage exclusions, and project provenance remain separate concerns.

Servers must support the byte ranges required by GDAL's `/vsicurl/` handler.
Missing CRS, invalid extents, and failed reads raise errors rather than
substituting a catalog bounding box. The pipeline's normal hook-error policy
still applies; this hook does not change global failure handling. Range access
avoids a full download when the raster layout permits it, but does not guarantee
a fixed amount of transferred data.
