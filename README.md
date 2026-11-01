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

---

**Fetchez** is an open-source, extensible Python framework for discovering, retrieving, caching, and processing geospatial data. Connect to public data providers, work with local files, or configure sources Fetchez has never seen before.

Use the same building blocks from the **command line**, **Python**, or **YAML**. Combine data sources with processing hooks, save workflows as recipes, and share reusable configurations with colleagues. Fetchez handles the data plumbing so you can focus on what to do with the data.

Originally developed for the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez now serves as a general-purpose geospatial ETL and workflow foundation for projects including [Globato](https://github.com/continuous-dems/globato) and [Transformez](https://github.com/continuous-dems/transformez).

## Table of Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Bring Your Own Data Source](#bring-your-own-data-source)
- [Python API](#python-api)
- [Extensibility](#extensibility)
- [Built on Fetchez](#built-on-fetchez)
- [Documentation & Community](#documentation--community)
- [License](#license)

---

## Install

Basic installation:

```bash
pip install fetchez
```

With optional provider and processing dependencies:

```bash
pip install 'fetchez[full]'
```

Some workflows require external command-line tools such as GDAL, which must be installed separately.

## Quick Start

Here's a complete example: discover elevation data around San Diego, download it, compress the rasters, and save the workflow for later reuse.

### Step 1: Discover data

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  list-only stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
```

This queries the Earth Search STAC catalog for Copernicus DEM assets. The `list-only` flag lets you inspect matching entries without downloading them. No Copernicus-specific Python module is needed—the generic `stac` handler works with any STAC catalog.

### Step 2: Fetch the data

Remove `list-only` to download the selected assets:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
```

Fetchez handles discovery, acquisition, caching, and entry processing in a unified workflow.

### Step 3: Process with hooks

Fetching is only the beginning. **Hooks** let you inspect, filter, transform, or process entries as they move through the pipeline. For example, this built-in `exec` hook runs GDAL on each downloaded raster:

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

The `{file}` variable refers to the acquired input; `{output}` is the staged destination for the new artifact. After a successful command, Fetchez publishes the output and passes it to subsequent hooks.

> **Note:** GDAL must be installed separately for this example.

### Step 4: Save and replay the workflow

Export your configured pipeline as a YAML recipe:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  --export san_diego_dem.yaml \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100 \
  exec \
  --cmd "gdal_translate {file} {output}" \
  --suffix "_trans"
```

Then run the recipe later:

```bash
fetchez run san_diego_dem.yaml
```

The exported recipe retains `list-only` for safe exploration. Remove that discovery-only step when you want the recipe to actually fetch data.

## Core Concepts

Fetchez composes workflows from several component types. Understanding these helps you build effective configurations:

| Component   | Purpose                                                                            |
|-------------|------------------------------------------------------------------------------------|
| **Sources** | Discover and retrieve data from catalogs, APIs, filesystems, or web indices        |
| **Hooks**   | Process entries as they pass through the pipeline (transform, filter, audit, etc.) |
| **Recipes** | YAML files that compose sources, hooks, and options into repeatable workflows      |
| **Bundles** | Pre-packaged collections of sources, hooks, and configurations for sharing         |
| **Readers** | Connect acquired data with downstream processing applications                      |

In `fetchez build`, components are composed left to right: hooks before the first source apply globally, while hooks after a source apply only to that source.

Explore registered components:

```bash
fetchez modules list          # Available data sources
fetchez modules bundles list  # Pre-configured bundles
fetchez hooks list            # Available hooks
fetchez hooks presets list    # Hook presets
```

## Bring Your Own Data Source

Fetchez prioritizes **configuration over code**. You can make new datasets accessible through YAML configuration rather than writing Python modules for every provider.

| Generic Module   | Best For                                                                                            |
|------------------|-----------------------------------------------------------------------------------------------------|
| **`local_fs`**   | Local files, file lists, and directories                                                            |
| **`http_index`** | HTTP directory listings and web pages with downloadable assets, with optional FRED spatial indexing |
| **`rest_api`**   | REST/JSON APIs, search responses, pagination, and discovered asset URLs                             |
| **`stac`**       | Spatial and temporal asset catalogs (imagery, elevation, lidar, cloud datasets)                     |
| **`thredds`**    | Scientific THREDDS catalogs and services (HTTPServer, NCSS, WCS, OPeNDAP)                           |

For example, accessing files from a ScienceBase record can be as simple as configuring `rest_api`:

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

These are generic interfaces—not every service follows the same conventions. Some sources require authentication or provider-specific settings; OPeNDAP endpoints need compatible readers rather than conventional downloads.

**Choosing the right approach:**

- Use a **built-in provider module** when it already captures provider-specific behavior
- Use a **generic module** to configure a new service via YAML
- Write a **custom module or hook** when the source needs specialized discovery or processing logic

## Python API

Fetchez works equally well from Python, alongside the CLI and declarative workflows. For example, this convenience API retrieves NOAA Electronic Nautical Chart files and applies hooks:

```python
import fetchez

files = fetchez.get(
    "charts",
    region=[-120, -118, 33, 34],
    hooks=["unzip", "filename_filter:match=.000", "audit"],
)
```

For custom applications, the module, reader, hook, and recipe interfaces provide more direct control. Python and YAML workflows build on the same extensible component system.

## Extensibility

Fetchez provides registries and execution lifecycles for:

- **Modules and bundles** — Discover data sources and curate reusable collections
- **Hooks and presets** — Inspect, filter, transform, and process entries, files, and streams
- **Readers and streams** — Connect acquired data with downstream processing
- **Recipes, modifiers, and schemas** — Compose, customize, and validate repeatable workflows
- **Plugins and extensions** — Add domain-specific behavior without changing Fetchez core

Contributions don't require Python plugins. A working YAML example, reusable source configuration, documentation for an unfamiliar API, or curated bundle can be a valuable addition. The goal is to make useful workflows easy to **discover, reproduce, adapt, and share**.

## Built on Fetchez

- **[Globato](https://github.com/continuous-dems/globato)** builds reproducible coastal and topobathymetric DEMs using Fetchez discovery and workflows, elevation-specific readers and hooks, MultiStack accumulation, and multi-resolution interpolation
- **[Transformez](https://github.com/continuous-dems/transformez)** integrates Fetchez data acquisition into spatial and vertical-reference transformation workflows
- **[IVERT](https://github.com/continuous-dems/ivert)** provides an independent elevation-validation workflow using ICESat-2 data

Fetchez grew from the CUDEM fetching engine, but its modules, hooks, recipes, and interfaces are designed for broader geospatial engineering applications.

## Documentation & Community

The [Fetchez documentation](https://fetchez.readthedocs.io/) expands on these examples, including generic data sources, recipes and bundles, hooks, Python integration, metadata, readers, and custom extensions.

Questions, ideas, and new source configurations are welcome in the [community chat](https://cudem.zulip.org/) or through [GitHub issues and pull requests](https://github.com/continuous-dems/fetchez).

## License

Fetchez is licensed under the [MIT License](LICENSE).

Copyright (c) 2010–2026 Regents of the University of Colorado.

---

*Made with ❤️ by the CUDEM team*
