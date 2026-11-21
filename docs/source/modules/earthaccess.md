# NASA Earthdata with `earthaccess`

Fetchez integrates the [earthaccess Python library](https://github.com/earthaccess-dev/earthaccess) to discover NASA Earth science collections and granules through the Common Metadata Repository (CMR), and to download selected data files through earthaccess-aware HTTP sessions. This makes NASA products available to ordinary Fetchez recipes, discovery caches, and downstream file and stream hooks without writing a separate module for each NASA dataset.

The module is useful for ICESat-2 photon and elevation products, lidar-derived terrain data, and other CMR-indexed resources. **Acquisition uses `earthaccess` rather than Fetchez's generic `Fetch` downloader**, so provider-specific Earthdata Login authentication and authorized redirects remain with the upstream library.

```{note}
"What the module supports today"

- **Discovery:** CMR collection metadata or granules, spatial/temporal filtering, asset selection, and `--discover-only`.
- **Acquisition:** local downloads of selected **external HTTP(S)** assets, with progress reporting, output locking, existing-file reuse, temporary files, and cancellation checks.
- **Not yet supported:** materializing `access="direct"` cloud/S3 assets or streaming remote COGs directly into downstream readers. Direct cloud links can be discovered, but not acquired by this module's current `fetch_entry()` implementation.
```

## Installation

Install Fetchez and the optional earthaccess dependency in the Python environment where you run Fetchez:

```console
pip install earthaccess
```

For authenticated downloads, configure a [NASA Earthdata Login](https://urs.earthdata.nasa.gov/) account. See [Authentication](#authentication) below. Public CMR metadata searches generally require no login.

## Quick start: NASA lidar-derived terrain data

This example uses the ORNL DAAC lidar-derived topography collection, **CMR collection ID `C4364851753-ORNL_CLOUD`**, and downloads matching **1 m bare-earth DTM GeoTIFFs** near San Diego, California:

```console
fetchez build -R loc:"san diego, ca" earthaccess \
  --concept-id C4364851753-ORNL_CLOUD \
  --count 10 \
  --links all \
  --link-pattern "*DTM.1m*.tif" \
  --access external \
  --auth auto \
  --outdir nasa_lidar
```

This workflow has been exercised with the updated module. It searches CMR for intersecting granules, selects matching GeoTIFF links, and downloads files to the module's output directory (for example, `nasa_lidar/earthaccess/`). To request DSM products instead, adjust the filename pattern to `*DSM*.tif` after inspecting the available asset names.

```{tip}
"Why 10 granules may produce fewer than 10 files"

`--count 10` limits **CMR granule search results**, not the number of files ultimately downloaded. `--links all` considers all selected data links for each granule, and `--link-pattern` then filters individual assets. A granule may have no matching files, one matching file, or several.
```

### Discover without downloading

Use the normal Fetchez discovery-only option to inspect matching entries before acquisition:

```console
fetchez build --discover-only -R loc:"san diego, ca" earthaccess \
  --concept-id C4364851753-ORNL_CLOUD \
  --count 10 \
  --links all \
  --link-pattern "*DTM.1m*.tif" \
  --access external \
  --auth none
```

`--discover-only` runs discovery and the appropriate metadata stages, but **does not download the selected files**. `auth=none` avoids login for public CMR discovery; for catalogs requiring an authenticated query, use a suitable authentication strategy instead.

## Example: ICESat-2 ATL03 data

The same module can retrieve ICESat-2 HDF5 granules, without a dedicated ICESat-2 fetch module:

```console
fetchez build -R loc:"san diego, ca" earthaccess \
  --short-name ATL03 \
  --count 5 \
  --links all \
  --link-pattern "*.h5" \
  --access external \
  --auth auto \
  --outdir icesat2_data
```

This ATL03 acquisition path has also been tested. Substitute `ATL06`, `ATL08`, or another CMR short name for other ICESat-2 products, and use `--temporal` and/or other CMR filters to narrow searches when appropriate. Product availability, version, and granule count depend on the region and query.

```{tip}
"For existing Earthdata workflows"

The `earthaccess` module offers a provider-maintained alternative for **discovery and download** of many products currently accessed through custom Earthdata clients. Migrating an existing workflow still requires validating its collection versions, filtering, authentication, and downstream file expectations. The older Fetchez `earthdata` module remains separate and is not replaced by this integration.
```

## How it fits into Fetchez

This module follows the normal `FetchModule` lifecycle:

1. **Discovery — `run()`:** query CMR and create serializable entries containing a source URL, output filename, data type, and CMR metadata. No primary data is downloaded.
2. **Acquisition — `fetch_entry(entry)`:** for `access="external"`, use an earthaccess-authorized HTTPS session (or an ordinary requests session when `auth="none"`) to download each selected asset. Downloads use temporary files, per-path locks, progress bars, and checks for cancellation and existing outputs.
3. **Processing:** successful entries continue through Fetchez's standard file, stream, collection, and finalize stages and can be used with downstream hooks and integrations.

The module overrides `fetch_entry()` rather than changing Fetchez core. This is the **reference pattern for provider-specific acquisition**: let the provider's own library handle its specialized HTTP authentication or API operations, while Fetchez handles workflow orchestration, entries, and processing.

Repeated runs can reuse existing nonempty outputs. Discovery caching and acquired-file reuse are separate mechanisms; the former stores search results, while the latter avoids repeating completed local downloads. `.lock` files may remain alongside downloaded data after the lock is released.

## Authentication

The `auth` option selects how the **earthaccess library** authenticates. Fetchez does not write credentials to `.netrc` or otherwise persist passwords.

| `auth` value | Behavior |
| --- | --- |
| `none` (default) | No earthaccess login. Useful for public CMR searches and openly downloadable files. Protected file downloads may fail. |
| `auto` | Try earthaccess's environment-based authentication, then `.netrc`; **no interactive prompt**. Recommended for batch jobs with configured credentials. |
| `netrc` | Use earthaccess's `.netrc` login strategy. |
| `environment` | Use earthaccess's environment login strategy. |
| `interactive` | Allow earthaccess to prompt for credentials. Appropriate for attended CLI sessions. |

For noninteractive workflows, supply credentials through a supported earthaccess environment configuration or a properly secured `.netrc` file and use `--auth auto`.

```{warning}
"Discovery-time login"

When `auth` is not `none`, the current module attempts earthaccess login during **`run()`**, before the CMR query, and again as needed when acquiring files. Therefore, `--discover-only --auth auto` can still require existing credentials, even though no data will be downloaded. Use `--auth none` for anonymous discovery where supported.
```

The module uses earthaccess's authorized HTTPS session for authenticated external links, including Earthdata Login redirects. This does **not** modify Fetchez's legacy `earthdata` module or its authentication helpers.

## Search and asset selection options

| Option | Purpose |
| --- | --- |
| `--resource` | `granules` (default) or `collections` (metadata-only). |
| `--short-name` | CMR collection short name, such as `ATL03`. |
| `--concept-id` | CMR collection or granule concept ID. Useful for an exact collection. |
| `--version` | Dataset version, where applicable. |
| `--count` | Maximum CMR search results; `-1` requests all results. |
| `--temporal` | Start/end ISO date or datetime range. |
| `--cloud-cover` | Cloud-cover min/max pair. |
| `--provider` | CMR provider ID. |
| `--cloud-hosted`, `--downloadable` | Additional CMR filtering. |
| `--granule-name` | Filter granules by name. |
| `--access` | `external` for HTTP(S) assets; `direct` for cloud-oriented links (discovery only at present). |
| `--links` | `first` (default) or `all` data links per granule. |
| `--link-pattern` | Filename or URL glob applied to selected data links, e.g. `*.h5` or `*DTM.1m*.tif`. |
| `--auth` | Authentication strategy described above. |

Python callers can additionally supply `polygon`, `point`, `include_browse`, and `search_kwargs`. Geographic regions supplied through the normal Fetchez `-R` option are converted to CMR bounding boxes in **west, south, east, north** order, unless a more specific polygon or point is supplied. The module also accepts inherited Fetchez time constraints where applicable.

By default, common browse/documentation links (such as JPEG, PNG, PDF, XML, and HTML) are excluded. `links="first"` selects the first *matching* candidate after filtering; use `links="all"` when a granule contains multiple relevant assets.

### Extra CMR search filters (Python)

`search_kwargs` provides a controlled allowlist of additional CMR parameters. It does not forward arbitrary Fetchez configuration to earthaccess:

```python
from fetchez.modules.earthaccess import EarthAccess

source = EarthAccess(
    short_name="ATL06",
    provider="NSIDC_CPRD",
    cloud_hosted=True,
    count=25,
    search_kwargs={"instrument": "ATLAS"},
)
source.run()  # discovery only
```

If the same CMR filter appears both as a dedicated constructor option and in `search_kwargs`, the module raises an error rather than silently choosing one.

## Python API

### Discover ICESat-2 granules

```python
from fetchez.modules.earthaccess import EarthAccess

source = EarthAccess(
    short_name="ATL03",
    temporal=("2024-01-01", "2024-01-31"),
    count=10,
    auth="none",  # public metadata query
    links="all",
    link_pattern="*.h5",
)
source.run()

for entry in source.results:
    print(entry["dst_fn"], entry["metadata"]["earthaccess"]["granule_id"])
```

`source.run()` is **discovery only**. Use the normal Fetchez pipeline (such as `fetchez build` in the CLI, or the orchestration API) to acquire and process the resulting entries. CMR granule metadata is retained under `entry["metadata"]["earthaccess"]`, including collection and granule identifiers, original provider metadata, and the selected access mode.

### Discover collection IDs before fetching

Collection discovery provides metadata, not downloadable file entries:

```python
catalog = EarthAccess(
    resource="collections",
    search_kwargs={"doi": "10.3334/ORNLDAAC/2523"},
    count=10,
    use_cache=False,
)
catalog.run()

for collection in catalog.collections:
    print(collection.get("meta", {}).get("concept-id"))
    print(collection.get("umm", {}).get("ShortName"))
```

Use an identified collection concept ID in a subsequent `resource="granules"` query. Collection results live in `catalog.collections`, not in `catalog.results`. Because Fetchez's base discovery cache stores ordinary entries, `use_cache=False` is recommended for interactive collection-metadata lookups when you need the `collections` property freshly populated.

## YAML recipe example

The module also works within a standard Fetchez recipe; this example discovers ICESat-2 granules and lets the recipe runner acquire matching assets:

```yaml
modules:
  - module: earthaccess
    args:
      short_name: ATL03
      temporal: ["2024-01-01", "2024-01-31"]
      count: 10
      links: all
      link_pattern: "*.h5"
      access: external
      auth: auto
```

Supply the geographic region through the recipe's normal region handling or the CLI region selector. If you need a specific collection version, add `version` after confirming its value in CMR.

## Current limitations and troubleshooting

- **Direct cloud links:** `access="direct"` can enumerate cloud/S3 links but `fetch_entry()` currently rejects non-external or non-HTTP(S) acquisitions. Use `access="external"` for local downloads.
- **No remote raster streaming:** downloaded GeoTIFFs can be consumed by downstream file/stream hooks, but this integration does not yet expose remote COGs through GDAL `/vsicurl/` or an S3-aware reader.
- **No generic HTTP resume:** incomplete transfers use temporary files that are cleaned up on failure; acquisition does not yet resume partial HTTP downloads. Existing completed files are reused.
- **Authentication failures:** verify the Earthdata Login account, chosen `auth` strategy, and access rights for the requested collection. `auth="auto"` intentionally does not prompt.
- **Few or no downloaded files:** remember that `count` applies to granules, then `link_pattern` filters assets. Start with `links="all"` and inspect discovered entry URLs to verify the dataset's filenames.
- **Large searches:** `count=-1` can produce many granules and substantial acquisition volume. Start with a smaller count and bounded region while testing.

For upstream earthaccess details, see the [earthaccess documentation](https://earthaccess.readthedocs.io/) and [NASA Earthdata](https://www.earthdata.nasa.gov/).
