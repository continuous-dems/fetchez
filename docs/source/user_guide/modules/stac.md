# Generic STAC module

The `stac` module connects any compatible STAC API to ordinary Fetchez entries. It supports
bounding-box searches from `-R`, collection and datetime searches, selection by asset key,
role or media type, and optional signed asset URLs.

Install the discovery dependency: `pip install pystac-client`. For Planetary Computer
signing, also install `planetary-computer`. For S3 presigning, install `boto3`.

## CLI: Earth Search / Copernicus DEM

```sh
fetchez build -R 'loc:san diego, ca' list-only stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 --assets data --limit 100
```

## YAML: Earth Search

```yaml
modules:
  - module: stac
    args:
      url: https://earth-search.aws.element84.com/v1
      collections: [cop-dem-glo-30]
      assets: [data]
      limit: 100
```

## YAML: Planetary Computer

```yaml
modules:
  - module: stac
    args:
      url: https://planetarycomputer.microsoft.com/api/stac/v1
      collections: [3dep-seamless]
      assets: [data]
      sign: planetary_computer
      limit: 100
```

## YAML: imagery with generic query

```yaml
modules:
  - module: stac
    args:
      url: https://earth-search.aws.element84.com/v1
      collections: [sentinel-2-c1-l2a]
      date: 2025-06-01/2025-08-31
      query:
        eo:cloud_cover:
          lt: 10
      assets: [red, green, blue]
      limit: 50
```

Collection names, asset keys, Query and CQL2 support vary by catalog; use the STAC browser
or service's collections endpoint to inspect them. `limit` counts **items**, not assets.

Without an explicit region, specify collections, IDs, a date or a filter; an unqualified
scan is refused. If no `assets` are specified, `visual`, `data`, then `analytic` are preferred;
otherwise all available assets are returned, matching the previous module's fallback.
Use `assets: all` to be explicit. `data_type` overrides the inferred entry classification.

**Note on caching:** Planetary Computer and S3 presigned URLs expire. Until Fetchez can
re-sign at acquisition time, disable discovery caching for these invocations when runs
may occur after signatures expire. `sign: none` avoids signing but does not grant access.

## Catalogs to explore

- Earth Search: https://earth-search.aws.element84.com/v1
- Microsoft Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1
- NASA CMR STAC: https://cmr.earthdata.nasa.gov/stac (provider-specific search endpoints)
- Copernicus Data Space: https://stac.dataspace.copernicus.eu/v1/

These are examples, not guaranteed anonymous download endpoints; availability and access
rules should be checked for the particular collection.
