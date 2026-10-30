# Fetchez

**Fetch, process, and compose geospatial data.**

**Fetchez** is an open-source, extensible Python framework for **discovering, retrieving, caching, and processing geospatial data**. Connect to public data providers, work with your own files, or configure a source that Fetchez has never seen before.

Use the same building blocks from the **command line, Python, or YAML**. Combine data sources with processing hooks, save workflows as recipes, and share reusable configurations with colleagues. Fetchez handles the data plumbing so you can focus on what to do with the data.

Originally developed for the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez now provides a general-purpose geospatial ETL and workflow foundation for applications including [Globato](https://github.com/continuous-dems/globato) and [Transformez](https://github.com/continuous-dems/transformez).

## Key Features

* **Unified Data Access:** Use a common interface to discover and retrieve data from more than 100 registered geospatial Modules.

* **Composable Pipelines:** Chain Modules, Bundles, Hooks, and Presets directly from the command line with `fetchez build`, from YAML recipes, or from Python.

* **Registry-Driven CLI:** Installed Fetchez components and extension-provided components become available dynamically without hard-coding commands into the core CLI.

* **Reusable Bundles & Presets:** Package common source collections and processing chains as declarative YAML components, with support for selective bundle expansion and configuration overrides.

* **Streaming Processing:** Filter, transform, inspect, and route data through manifest, file, stream, and collection processing stages.

* **Reproducible Recipes:** Export ad-hoc pipelines as YAML and reproduce them later with `fetchez run`.

* **Parallel Fetching & Caching:** Download efficiently with multi-threaded execution, retries, resumable transfers, and shared caches.

* **Extensible Architecture:** Add Modules, Hooks, Streams, Readers, Bundles, Presets, Modifiers, Schemas, and domain-specific extensions through Python packages or local plugins.

## Quickstart

**Installation:**

```bash
pip install fetchez
```

### Command Line Interface

Discover available data from a registered Fetchez component, in this case using the builtin [`stac` module](user_guide/modules/stac.md):

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  list_only \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
```

In `fetchez build`, components are composed from left to right: hooks before the first source apply globally, while [hooks and presets](user_guide/hooks_and_presets.md) placed after a [module or bundle](user_guide/modules_and_bundles.md) apply only to that source.

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  audit \  # Hook (Global)
  stac \   # Module
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
  exec \   # Hook (Attched to the `stac` module
  --cmd "gdal_translate {file} {output}"
  --suffix "_trans"
```

Export the same pipeline as a reusable recipe:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  --export "sd_cop.yaml" \
  audit \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 100
  exec \
  --cmd "gdal_translate {file} {output}"
  --suffix "_trans"
```

Run it later with:

```bash
fetchez run sd_cop.yaml
```

### Python API:

```python
>>> import fetchez

>>> # Search registered components
>>> bathy_components = fetchez.search("bathymetry")

>>> bathy_components.keys()
dict_keys(['modules', 'bundles', 'hooks', 'recipes', 'schemas', 'modifiers', 'presets', 'streams', 'readers', 'profiles', 'data_types', 'detectors'])

>>> # Search registered modules
>>> bathy_results = fetchez.search_modules("bathymetry")

>>> # Get the info dictionary about the `nos_hydro` module
>>> nos_info = fetchez.registry.ModuleRegistry.get_info("nos_hydro")

>>> # Fetch NOS Hydrographic Data (Returns list of fetched local file paths)
>>> files = fetchez.get("nos_hydro", region=[-120, -118, 33, 34], min_year=2020)

>>> # Fetch Electronic Nautical Chart data from NOAA,
>>> # extract the fetched data, filter the results by the .000 file extension
>>> # and write a detailed audit process.
>>> files = fetchez.get("charts", region=[-120, -118, 33, 34], hooks=['extract', 'filename_filter:match=.000,stage="file"', 'audit'])
```

## How Fetchez Components Fits Together

Fetchez workflows are assembled from a small set of reusable component types:

* **Modules** discover and retrieve data.
  * **Bundles** compose reusable groups of Modules.
* **Hooks** process data as it moves through the pipeline.
  * **Presets** package reusable Hook chains.
* **Recipes** describe complete reproducible workflows.
  * **Modifiers** alter assembled recipes before execution.
  * **Schemas** validate workflows against domain requirements.
* **Streams** provide reusable data access and processing interfaces.
  * **Data Types** set data entry types to link entries to profiles and readers.
  * **Readers** provide data specific stream adaptors.
  * **Profiles** link data entries to stream readers.

The same component model is shared by the Python API, YAML recipes, and the `fetchez build` command-line interface.

## Learn More

Read the [User Guide](user_guide/index.md) to install, discover data sources and modules and understand how Fetchez works; from data source modules, processing hooks, reporoducable recipes, to the CLI, API and more.


```{toctree}
:maxdepth: 2
:hidden:
:caption: User Guide:

user_guide/index
api/index
contribute/index
modules/index
```

Indices and tables
==================

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
