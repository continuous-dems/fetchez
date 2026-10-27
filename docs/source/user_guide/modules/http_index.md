# Generic HTTP discovery (`http_index`)

`http_index` discovers downloadable file links from plain HTML pages and indexed directories. It registers normal Fetchez entries; it does not download assets during discovery.

## One-off USGS or publication page: no spatial index needed

```yaml
modules:
  - module: http_index
    args:
      url: https://example.org/publication/data/
      pattern:
        - '*.zip'
        - '*.tif'
        - '*.txt'
      exclude: ['*thumbnail*']
      data_type: file
```

Run the bundle normally, **without `-R`**. All matching links from that page will be registered. When no `footprint` is configured, even an explicit region does not exclude discovered links: no per-file footprint is known.

To visit linked catalog pages (not the entire web site):

```yaml
      recursive: true
      follow_pattern:
        - '*data_catalog*'
        - '*/data/'
      max_depth: 2
      max_pages: 50
```

Crawling is same-origin only, depth/page/asset limited, and requires explicit `follow_pattern` to traverse linked pages. It is intended for static HTML, not JavaScript-generated catalogs.

## Shared study-area footprint (optional)

```yaml
modules:
  - module: http_index
    args:
      url: https://example.org/coastal-study/
      pattern: '*.zip'
      footprint:
        method: static
        bounds: [-120, -117, 32, 35]  # Fetchez w/e/s/n; approximation
```

With `-R`, a discovered asset is emitted only if its known footprint intersects the requested region. Without `-R`, **all** matches are emitted. Set `filter_region: false` to intentionally ignore an explicitly requested region.

## Reusable WSF index (optional)

```yaml
modules:
  - module: http_index
    args:
      url: https://download.geoservice.dlr.de/WSF2019/files/
      pattern: '*.tif'
      exclude: '*cog*'
      index: true
      index_name: wsf2019_custom
      footprint:
        method: filename
        regex: 'WSF2019_v1_(?P<x>-?\d+)_(?P<y>-?\d+)\.tif'
        width: 2
        height: 2
      data_type: raster
```

`index: true` requires a footprint strategy (`static`, `filename`, or `fgdc`). The first run crawls and creates FRED GeoJSON, defaulting to `~/.fetchez/data/<index_name>.geojson` when no `index_path` is supplied. Later runs use FRED for regional queries; without `-R`, they return all indexed assets. Use `update: true` to refresh.

**Important:** `static` bounds are a source-level approximation, not measured coverage for each file. Files with no valid footprint are omitted from a spatial index, although they are included in ordinary non-indexed crawls. All files on a page must be in the same origin as the page; downloads at other hosts require a separate source definition.

The `modules` examples show module configurations; wrap them with your project's usual bundle keys as needed.
