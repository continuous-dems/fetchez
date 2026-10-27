# Generic THREDDS module (`thredds`)

The `thredds` module supports HTTPServer file discovery, NCSS grid subsetting,
WCS GetCoverage, and OPeNDAP URL registration. It doesn't require a new reader.
Only HTTPServer, NCSS, and WCS endpoints are intended for normal HTTP downloads;
OPeNDAP requires a compatible remote reader.

## Compare with `ncei_thredds`

```yaml
modules:
  - module: thredds
    args:
      url: https://www.ngdc.noaa.gov/thredds/catalog/regional/catalog.xml
      service: HTTPServer
      dataset: bathy
      spatial: strict
      iso_fallback: true
      limit: 100
```

Try with `-R` and compare with `ncei_thredds --catalog regional` and a corresponding
`--dataset` filter. `spatial: strict` is closest to the old module's skip-if-no-footprint
policy; `iso_fallback: true` optionally requests ISO footprints where catalog bounds
are unavailable. The generic module intentionally does not infer vertical datums or
publication years from NCEI-specific filenames.

**Important:** If the catalog includes aggregation datasets, they may have different
service access or geometry from individual files. Compare URLs/selected dataset IDs,
not just file counts.

### NCEI WCS alternative

```yaml
modules:
  - module: thredds
    args:
      url: https://www.ngdc.noaa.gov/thredds/catalog/regional/catalog.xml
      service: WCS
      spatial: strict
      iso_fallback: true
      parameters:
        coverage: z
        format: geotiff_float
        version: 1.0.0
      limit: 100
```

The generated query has WGS84 `bbox` coordinates in min-lon,min-lat,max-lon,max-lat
order. Exact WCS coverage identifiers and supported formats vary by server.

## Compare with dist2coast (direct NCSS endpoint)

```yaml
modules:
  - module: thredds
    args:
      url: https://pae-paha.pacioos.hawaii.edu/thredds/ncss/grid/dist2coast_1deg
      service: NCSS
      parameters:
        var: dist
        addLatLon: true
        accept: netcdf
      data_type: netcdf
```

Run this with an explicit `-R`. The resulting NCSS query uses `north`, `south`,
`east`, and `west` and should request the same data subset as `dist2coast`'s
`variant: base` (output filename differs). Substitute `dist2coast_1deg_ocean` or
`dist2coast_1deg_land` for the other variants.

## Test on a non-elevation catalog

### NOAA NCEI marine and ocean data

```yaml
modules:
  - module: thredds
    args:
      url: https://www.ncei.noaa.gov/thredds/catalog/catalog.xml
      service: HTTPServer
      recursive: true
      max_depth: 3
      max_catalogs: 40
      pattern: '*.nc'
      spatial: known
      limit: 20
```

### NOAA Pacific OceanWatch catalog

```yaml
modules:
  - module: thredds
    args:
      url: https://oceanwatch.pifsc.noaa.gov/thredds/catalog.xml
      service: OPENDAP
      recursive: true
      max_depth: 2
      max_catalogs: 25
      limit: 10
```

Both are **exploratory configurations**; dataset and service availability should be
verified on a live server. `service: OPENDAP` registers remote URLs, not downloaded
NetCDF files. Consider a narrow `dataset` filter, `pattern`, and crawl limits when
querying large catalogs.

## Main options

- `url` / `catalog_url`: THREDDS XML catalog or direct NCSS/WCS dataset URL.
- `service`: `HTTPServer` (default), `NCSS`, `WCS`, or `OPENDAP`.
- `pattern`: glob(s) or substring(s) matching dataset names.
- `dataset`: case-insensitive dataset name/ID substring.
- `spatial`: `known` (filter where bounds exist; retain unknown), `strict` (exclude
  unknown when `-R` supplied), `none` (disable spatial filtering).
- `iso_fallback`: when `true`, try `core.iso_xml` for missing catalog bounds.
- `recursive`, `max_depth`, `max_catalogs`, `limit`: limit traversal/work.
- `parameters`: mapping of NCSS/WCS request parameters, including `var`, `time`,
  `time_start`, `time_end`, `accept`, `coverage`, etc., as supported by the server.
- `data_type`: override the default Fetchez entry data type.

**Not implemented:** discovery of temporal coverage, automatic time-series sampling,
NCSS point/profile requests, authentication, or reading OPeNDAP payloads. These can
be pursued later when the generic readers are ready. Catalog `geospatialCoverage`
is used only when bounds are directly or inherited within the dataset hierarchy.
