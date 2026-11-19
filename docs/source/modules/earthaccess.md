# Fetchez / earthaccess integration

This module wraps NASA's `earthaccess` library for CMR discovery and registers
matching granule assets as ordinary Fetchez entries. Install the optional backend
with `pip install earthaccess`.

## Python: search ICESat-2 granules

```python
from fetchez.modules.earthaccess import EarthAccess

source = EarthAccess(
    short_name='ATL03',
    temporal=('2024-01-01', '2024-01-31'),
    count=10,
    auth='none',  # anonymous CMR search
    links='all',
    link_pattern='*.h5',
)
source.run()
for entry in source.results:
    print(entry['dst_fn'], entry['metadata']['earthaccess']['granule_id'])
```

Fetchez region constraints (including `wgs_region` from the base module) are
translated to CMR bounding-box order `(west, south, east, north)`.

## YAML recipe (new options)

```yaml
modules:
  - module: earthaccess
    args:
      short_name: ATL03
      version: '006'  # illustrative: confirm current collection version in CMR
      temporal: ['2024-01-01', '2024-01-31']
      count: 10
      links: all
      link_pattern: '*.h5'
      auth: none
```

Use the normal Fetchez recipe/CLI region selector to constrain geography.

## Collection discovery (Python-only metadata mode)

```python
catalog = EarthAccess(resource='collections', short_name='ATL03', count=10)
catalog.run()
for collection in catalog.collections:
    print(collection.get('meta', {}).get('concept-id'))
```

Collection discovery is metadata-only: it intentionally does *not* produce
file-acquisition entries. This interface is meant for an interactive Python
caller, not a recipe that expects to download collection search results.

## More CMR search filters

```python
source = EarthAccess(
    short_name='ATL06',
    provider='NSIDC_CPRD',
    cloud_hosted=True,
    count=25,
    search_kwargs={'instrument': 'ATLAS'},
)
source.run()
```

`search_kwargs` is an explicit allowlist of supported additional CMR filters;
it is not an arbitrary forwarding of unrelated Fetchez arguments.
