# Generic REST APIs with Fetchez

Fetchez's `rest_api` module connects ordinary JSON/HTTP services to the same
fetch, cache, hook, and recipe machinery as provider-specific modules. Most
services can be configured in YAML without writing Python. The module performs
**resource discovery** and emits normal Fetchez entries; downstream hooks and
the standard fetcher handle the assets.

> This guide describes the supplied `fetchez/modules/rest.py` implementation
> (October 2026). Examples of provider responses are illustrative; actual API
> fields and permissions should be checked before creating a production bundle.

## Choose a mode

| `mode` | Behavior | Typical use |
| --- | --- | --- |
| `response` (default) | Register the API response as an asset. GET responses are fetched by the standard runtime; POST responses are written locally during module execution. | Download GeoJSON, JSON, or a generated API result. |
| `discover` | Parse JSON records and register the files referenced by them. | Search data catalogs, find raster/ZIP/point-cloud assets. |

A query returning *no* matches is valid and different from a failed request.
The module sets `_discovery_failed` for errors caught by its main `run()`
handler so the base discovery cache does not treat them as successful results.
See **Current limitations** for partial detail-request failures.

## Quick start: JSON discovery

Suppose `https://data.example.org/api/surveys` returns:

```json
{
  "results": [
    {
      "id": "survey-001",
      "name": "Coastal survey",
      "links": {"download": "https://data.example.org/files/001.tif"},
      "properties": {"year": 2024}
    }
  ]
}
```

A single-module bundle/recipe configuration could contain:

```yaml
modules:
  - module: rest_api
    args:
      url: https://data.example.org/api/surveys
      mode: discover
      parameters:
        type: bathymetry
      results_path: results
      url_field: links.download
      filename_field: name
      id_field: id
      metadata_fields:
        survey_year: properties.year
      data_type: raster
      limit: 50
```

`results_path` locates an array of records; `url_field` selects the download
link within each record. Nested selectors use dot notation, e.g.
`properties.download.href`, and numeric array indices, e.g. `files.0.url`.
For a string `filename_field`, note that filename sanitization and a stable
hash suffix are applied; prefer an actual filename (with extension) when
available. For the sample above, omitting `filename_field: name` would be
preferable if you want to keep the `.tif` extension automatically.

The generic `modules` snippet shows the per-module configuration. The outer
file name, top-level bundle metadata, and registration path should match the
BundleRegistry conventions in your checkout.

### Run a registered bundle

The project's existing build pipeline accepts named bundles, e.g.:

```console
fetchez --verbose build -R 'loc:santa monica, ca' test-rest
```

Here `test-rest` is the name of a bundle already registered with Fetchez;
`-R` supplies the search region. Replace it with the registered name of your
own source. You can combine the module with ordinary hooks in the containing
recipe or bundle.

For CLI options on the generic module itself, inspect the commands exposed by
your installed version:

```console
fetchez --help
```

The `@cli_opts` metadata declares `url`, `method`, `parameters`, `headers`,
`body`, `mode`, `results_path`, `url_field`, `filename_field`, `id_field`,
`metadata_fields`, `data_type`, `pagination`, `detail`, and `limit`. The exact
command nesting and argument serialization are controlled by your installed
CLI/registry version. For complex nested mappings, a YAML bundle is generally
more readable than CLI quoting.

### Python usage

```python
from fetchez.modules.rest import RestAPIModule

module = RestAPIModule(
    url="https://data.example.org/api/surveys",
    mode="discover",
    parameters={"type": "bathymetry"},
    results_path="results",
    url_field="links.download",
    id_field="id",
    data_type="raster",
)
module.run()
for entry in module.results:
    print(entry["url"], entry["dst_fn"])
```

This performs discovery. To download assets and execute hooks, run the module
through Fetchez's usual build/recipe pipeline. The base `FetchModule` wraps
`run()` for cached discovery when used in the real package.

## Region placeholders

Spatial request formatting is handled by the shared `Region` object, not
provider-specific parsing inside the REST module. Use `{region:<style>}` in
`url`, `parameters`, or `body` values. The module copies the supplied region,
then transforms to `region_srs` (default `EPSG:4326`) before serialization.

```yaml
modules:
  - module: rest_api
    args:
      url: https://data.example.org/api/search
      mode: discover
      parameters:
        bbox: "{region:bbox}"
        filter: active
      results_path: results
      url_field: download_url
```

Common styles provided by the updated `Region` implementation:

| Placeholder | Result |
| --- | --- |
| `{region:bbox}` | `west,south,east,north` |
| `{region:region}` | `west,east,south,north` |
| `{region:bbox_wesn}` | Explicit alias for the preceding order (if enabled in your updated `Region`) |
| `{region:wkt}` | Polygon WKT for the rectangular bounds |
| `{region:geojson}` | Polygon GeoJSON |
| `{region:arcgis}` | ArcGIS envelope JSON |

A *whole-value* `{region:geojson}` or `{region:arcgis}` placeholder yields a
native dictionary suitable for POST JSON bodies. Embedded placeholders inside
longer strings yield text. A region placeholder **requires an explicitly
supplied region with a known CRS** when `region_srs` is enabled; the base
module's implicit world extent does not count as explicit input.

### ArcGIS FeatureServer query example

```yaml
modules:
  - module: rest_api
    args:
      url: https://example.org/arcgis/rest/services/Surveys/FeatureServer/0/query
      mode: response
      out_ext: .geojson
      parameters:
        f: geojson
        where: "1=1"
        outFields: "*"
        geometry: "{region:arcgis}"
        geometryType: esriGeometryEnvelope
        spatialRel: esriSpatialRelIntersects
        inSR: 4326
```

This example illustrates parameter interpolation; a real endpoint may expect
an envelope string instead of JSON, require a token, or use a different
response format. Keep `inSR` aligned with `region_srs`.

### Repeated query parameters

For APIs that allow repeated keys (including ScienceBase filters), configure
`parameters` as a list of pairs rather than a mapping:

```yaml
parameters:
  - [filter, public]
  - [filter, "spatialQuery={region:wkt}"]
```

This preserves *both* `filter` query parameters. The precise filter expression
is provider-dependent and should be tested against the provider's API.

## Two-stage discovery: USGS ScienceBase

ScienceBase catalog search returns relatively lightweight item records;
download attachments are typically exposed on individual item detail
responses. `detail` tells Fetchez to follow each item's URL and enumerate its
`files` list.

```yaml
modules:
  - module: rest_api
    args:
      url: https://www.sciencebase.gov/catalog/items
      mode: discover
      parameters:
        q: bathymetry
        format: json
        max: 20
        filter: "spatialQuery={region:wkt}"
      results_path: items
      id_field: id
      metadata_fields:
        title: title
        summary: summary
      detail:
        url_field: link.url
        parameters:
          format: json
        results_path: files
        asset_url_field: url
        filename_field: name
        metadata_fields:
          size: size
          content_type: contentType
      data_type: file
      limit: 100
```

The module first requests `/catalog/items`, then follows each `link.url` and
parses the detailed item's `files`. Each attachment produces a separate normal
Fetchez entry. The parent item's `source_id`, `title`, and `summary` are carried
into the attachment metadata; size and content type come from each file record.

**Important:** `detail.parameters` is the correct current key, not
`detail.params`. Unlike top-level `parameters`, the supplied implementation
currently does *not* interpolate `{region:...}` placeholders in detail
parameters. This is an identified follow-up improvement.

`limit` caps **registered assets**, not the number of searched items or detail
requests; one catalog item may contain several files. The module does not
recursively descend through ScienceBase child items.

## Pagination

Pagination is optional; configure it when the service returns paged results.

**Next-link** (the JSON response contains `next`):

```yaml
pagination:
  type: next
  path: next
  max_pages: 20
```

**Offset pages** (service uses `offset` and returns batches):

```yaml
parameters:
  offset: 0
  limit: 25
pagination:
  type: offset
  param: offset
  page_size: 25
  start: 0
  max_pages: 20
```

**Numbered pages** (service uses `page`):

```yaml
parameters:
  page: 1
pagination:
  type: page
  param: page
  page_size: 25
  start: 1
  max_pages: 20
```

For numbered/offset pagination, the module decides whether to stop based on
whether a page returns fewer records than `page_size`. Set the page size to
match the server's actual page size. If your API exposes a `next` link, prefer
that instead. `max_pages` is a safety bound, not a desired page count.

## Response mode and POST requests

A straightforward response download:

```yaml
modules:
  - module: rest_api
    args:
      url: https://example.org/geojson
      mode: response
      out_ext: .geojson
      parameters:
        bbox: "{region:bbox}"
```

For JSON POST requests, use `method: POST` and `body`:

```yaml
modules:
  - module: rest_api
    args:
      url: https://example.org/search
      method: POST
      mode: response
      out_ext: .json
      body:
        geometry: "{region:geojson}"
        filters:
          category: elevation
```

In current `response` mode, GET entries are registered for later download,
while POST responses are immediately saved as local files. Treat cached POST
response entries carefully: if the local materialized file disappears while
its discovery manifest remains cached, reusing that manifest may not recreate
the file.

## Configuration reference

| Option | Purpose |
| --- | --- |
| `url` | Required endpoint URL; supports region placeholders. |
| `mode` | `response` (default) or `discover`. |
| `method` | `GET` (default) or `POST`. |
| `headers` | Optional JSON-compatible request headers. Avoid committing tokens. |
| `parameters` | Query mapping or list of `[key, value]` pairs. |
| `body` | Optional JSON request body, used for POST. |
| `results_path` | Dot path to object/array of search records. |
| `url_field` | Download-URL path for direct discovery. |
| `filename_field` | Optional filename path for direct discovery. |
| `id_field` | Optional stable identifier path, copied as `source_id`. |
| `metadata_fields` | Mapping of metadata names to paths. |
| `detail` | Secondary request mapping (see ScienceBase example). |
| `data_type` | Entry type (default `file`); use a type understood by your workflows. |
| `pagination` | `type: next|offset|page`, plus options shown above. |
| `limit` | Max number of registered discovered entries (default 500). |
| `out_ext` | Output suffix for response mode (default `.json`). |
| `timeout` | Request timeout in seconds (default 30). |
| `region_srs` | CRS used when interpolating region values (default `EPSG:4326`). |

The current module's constructor argument is **`parameters`**, not `params`.
`params` is a separate argument in the base `FetchModule` and does not build
REST query strings here.

## Troubleshooting

**Search returns items, but no files are registered.** Confirm whether the
search records actually contain download links. If they only contain item URLs
and IDs, configure `detail` as in the ScienceBase example. Inspect the actual
JSON before choosing `results_path` and `url_field`.

**`Skipping record without URL`**. The configured field path doesn't exist
in that record. Paths operate on a single record *after* `results_path` has
selected the record array.

**Region placeholder failure.** Supply `-R` or `src_region` explicitly and
ensure that `Region.srs` is known. The module cannot label/reproject unknown
coordinates safely.

**Changes appear to have no effect.** The base module caches successful
discovery. Invalidate the relevant discovery cache entry, disable it with the
base module's cache controls, or change configuration and rerun.

## Design principle

REST knows how to **request and discover**; `Region` knows how to **encode
spatial extents**; YAML maps a provider's response shape into Fetchez entries;
and the existing fetch, hook, cache, and stream machinery performs the actual
geospatial ETL. Simple providers need only configuration, while complex ones
can still use dedicated Python modules.
