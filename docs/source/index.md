# Fetchez Documentation

**Fetch, process, and compose geospatial data.**

**Fetchez** is a robust, highly modular and extensible Python framework designed to orchestrate complex geospatial data engineering workflows.

Fetchez is part of the [Continuous DEMs Project](https://continuous-dems.readthedocs.io/), an ecosystem of tools for modern, continuous digital elevation model generation.

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

Compose an ad-hoc pipeline from registered Fetchez components:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    audit \
    copernicus \
    multibeam
```

Here `audit` is a global processing hook because it appears before the first data source.

Hooks and presets placed after a Module or Bundle apply only to that source:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    copernicus raster_warp --res 1s \
    multibeam
```

Export the same pipeline as a reusable recipe:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    --export miami.yaml \
    audit copernicus multibeam
```

Run it later with:

```bash
fetchez run miami.yaml
```

### Python API:

```python
import fetchez

# Search
bathy_mods = fetchez.search("bathymetry")

# Get Data (Returns list of local file paths)
files = fetchez.get("nos_hydro", region=[-120, -118, 33, 34], min_year=2020)

# Fetch Electronic Nautical Chart data from NOAA
files = fetchez.get("charts", region=[-120, -118, 33, 34], hooks=['unzip', 'filename_filter:match=.000,stage="pre"', 'audit'])
```

## How Fetchez Fits Together

Fetchez workflows are assembled from a small set of reusable component types:

* **Modules** discover and retrieve data.
* **Bundles** compose reusable groups of Modules.
* **Hooks** process data as it moves through the pipeline.
* **Presets** package reusable Hook chains.
* **Recipes** describe complete reproducible workflows.
* **Modifiers** alter assembled recipes before execution.
* **Schemas** validate workflows against domain requirements.
* **Streams and Readers** provide reusable data access and processing interfaces.

The same component model is shared by the Python API, YAML recipes, and the `fetchez build` command-line interface.

## Learn More

Interested in how the `fetchez` framework works? Read the [User Guide](user_guide/index.md) guide to learn about modules, hooks, recipes and more.


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
