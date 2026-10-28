<p align="center">
  <a href="https://fetchez.readthedocs.io/">
    <img src="https://raw.githubusercontent.com/continuous-dems/fetchez/refs/heads/main/docs/source/_static/fetchez-logo.svg" height="80" alt="Fetchez logo">
  </a>
</p>
<h1 align="center">Fetchez</h1>
<p align="center"><strong>Fetch. Cache. Deliver.</strong></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-yellow.svg" alt="Python 3.12+"></a>
  <a href="https://badge.fury.io/py/fetchez"><img src="https://badge.fury.io/py/fetchez.svg" alt="PyPI version"></a>
  <a href="https://anaconda.org/conda-forge/fetchez"><img src="https://img.shields.io/conda/vn/conda-forge/fetchez.svg" alt="Conda version"></a>
  <a href="https://cudem.zulip.org"><img src="https://img.shields.io/badge/zulip-join_chat-brightgreen.svg" alt="Join project chat"></a>
  <a href="https://doi.org/10.5281/zenodo.22130386"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.22130386.svg" alt="DOI"></a>
</p>

**Fetchez** is an open-source, extensible Python framework for **discovering, retrieving, caching, and processing geospatial data**. Connect to public data providers, work with your own files, or configure a source that Fetchez has never seen before—without writing a new Python downloader.

Use the same building blocks from the **command line, Python, or YAML**. Combine data sources with processing hooks, save workflows as recipes, and share reusable configurations with colleagues. Fetchez handles the data plumbing so you can focus on what to do with the data.

Originally developed for the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez now provides a general-purpose geospatial ETL and workflow foundation for applications including [Globato](https://github.com/continuous-dems/globato) and [Transformez](https://github.com/continuous-dems/transformez).

## Install

```bash
pip install fetchez
```

For optional provider and processing dependencies:

```bash
pip install 'fetchez[full]'
```

Some workflows also use external command-line programs such as GDAL. These are installed separately.

## From discovery to a reusable workflow

Imagine you need elevation data around San Diego. You could look for a prebuilt provider module—but with Fetchez, you can also query a public STAC catalog directly.

### 1. Discover data

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  list-only stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
```

This uses the generic `stac` module to search the Earth Search catalog for Copernicus DEM assets. `list-only` lets you inspect matching entries without downloading them. The source is configured at runtime; no Copernicus-specific Python module is needed.

### 2. Fetch what you found

Remove `list-only` to let Fetchez retrieve the selected assets:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
```

Fetchez brings discovery and acquisition together, using its normal download, cache, and entry-processing workflow. As with any remote catalog, the number and size of matching assets depend on the selected area and catalog contents.

### 3. Process files with hooks

Fetching is only the beginning. **Hooks** let you inspect, filter, unpack, transform, or otherwise process entries as they move through the pipeline.

For example, the built-in `exec` hook can run GDAL on each downloaded raster and register the result as an output artifact. Its configuration can look like this:

```yaml
hook: exec
args:
  cmd:
    - gdal_translate
    - -of
    - GTiff
    - -co
    - COMPRESS=LZW
    - "{file}"
    - "{output}"
  output:
    suffix: _compressed
    extension: .tif
    update_entry: true
```

`{file}` is the acquired input; `{output}` is the staged destination for the new artifact. After a successful command, Fetchez publishes the output and can pass it to subsequent hooks. **GDAL must be installed separately** for this example.

The hook configuration above is a component fragment, not a complete recipe. Fetchez also supports hooks such as `audit` for observing a workflow:

```bash
fetchez build -R 'loc:Miami, FL' audit copernicus multibeam
```

In `fetchez build`, components are composed from left to right: hooks before the first source apply globally, while hooks after a source apply to that source.

### 4. Save and replay the pipeline

You don't have to rebuild a workflow by hand each time. Export a configured pipeline as a YAML recipe:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  --export san_diego_dem.yaml \
  list-only stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
```

Run the exported recipe later:

```bash
fetchez run san_diego_dem.yaml
```

The exported example retains `list-only` for safe exploration. Remove that discovery-only step when you want the recipe to fetch data.

A generic source can also be expressed as a small YAML **component configuration**:

```yaml
module: stac
args:
  url: https://earth-search.aws.element84.com/v1
  collections: cop-dem-glo-30
  assets: data
  limit: 100
```

That fragment describes a source, not an entire runnable recipe or registered bundle. The full recipe and bundle formats let you collect sources, hooks, and options into reusable configurations. Share those configurations as examples or bundles without asking everyone to install a new provider module.

## Bring your own data source

A major goal of Fetchez is to make new datasets accessible **through configuration first**, rather than requiring new Python code for every provider.

| Generic module | Best for |
| --- | --- |
| **`local_fs`** | Files, file lists, and directories already on your machine |
| **`http_index`** | HTTP directory listings and web pages linking to downloadable assets, with optional FRED spatial indexing |
| **`rest_api`** | REST/JSON APIs, search responses, pagination, and discovered asset URLs |
| **`stac`** | Spatial and temporal asset catalogs, including imagery, elevation, lidar, and other cloud datasets |
| **`thredds`** | Scientific THREDDS catalogs and services including HTTPServer, NCSS, WCS, and OPeNDAP |

For example, accessing files advertised by a ScienceBase record can be as simple as configuring `rest_api`:

```yaml
module: rest_api
args:
  url: https://www.sciencebase.gov/catalog/item/5a710077e4b0a9a2e9dafd52
  mode: discover
  parameters:
    format: json
  results_path: files
  url_field: url
  filename_field: name
```

These are general interfaces, not a claim that every service uses the same conventions. Some sources require authentication or provider-specific settings; OPeNDAP endpoints, for instance, need compatible readers rather than a conventional file download.

Prefer a **built-in provider module** when it already captures useful provider-specific behavior. Use a **generic module** to configure a new service. Write a **custom module or hook** when the source genuinely needs specialized discovery or processing logic.

## Python is a first-class interface

Fetchez can also be used from Python, alongside the CLI and declarative workflows. For example, its convenience API can retrieve NOAA Electronic Nautical Chart files and apply hooks:

```python
import fetchez

files = fetchez.get(
    "charts",
    region=[-120, -118, 33, 34],
    hooks=["unzip", "filename_filter:match=.000", "audit"],
)
```

For custom applications, the module, reader, hook, and recipe interfaces provide more direct control. Python workflows and declarative YAML workflows build on the same extensible component system.

## Designed to be extended—and shared

Fetchez provides more than source modules. Its registries and execution lifecycle support:

- **Modules and bundles** to discover data sources and curate reusable collections.
- **Hooks and presets** to inspect, filter, transform, and process entries, files, and streams.
- **Readers and streams** to connect acquired data with downstream processing.
- **Recipes, modifiers, and schemas** to compose, customize, and validate repeatable workflows.
- **Plugins and extensions** to add domain-specific behavior without changing Fetchez core.

You don't need to begin with a Python plugin. A working YAML example, a reusable source configuration, documentation for an unfamiliar API, or a curated bundle can be a valuable contribution. The goal is to make useful workflows easy to **discover, reproduce, adapt, and share**.

Explore registered components with:

```bash
fetchez modules list
fetchez modules bundles list
fetchez hooks list
fetchez hooks presets list
```

## Built on Fetchez

- **[Globato](https://github.com/continuous-dems/globato)** builds reproducible coastal and topobathymetric DEMs using Fetchez discovery and workflows, elevation-specific readers and hooks, MultiStack accumulation, and multi-resolution interpolation.
- **[Transformez](https://github.com/continuous-dems/transformez)** integrates Fetchez data acquisition into spatial and vertical-reference transformation workflows.
- **[IVERT](https://github.com/continuous-dems/ivert)** provides an independent elevation-validation workflow using ICESat-2 data.

Fetchez grew from the CUDEM fetching engine, but its modules, hooks, recipes, and interfaces are designed for much broader geospatial engineering applications.

## Documentation and community

The [Fetchez documentation](https://fetchez.readthedocs.io/) expands on the examples here, including generic data sources, recipes and bundles, hooks, Python integration, metadata, readers, and custom extensions.

Questions, ideas, and new source configurations are welcome in the [community chat](https://cudem.zulip.org/) or through [GitHub issues and pull requests](https://github.com/continuous-dems/fetchez).

## License

Fetchez is licensed under the [MIT License](LICENSE).

Copyright (c) 2010–2026 Regents of the University of Colorado.
