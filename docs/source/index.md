# Fetchez Documentation

**Fetch geospatial data with ease.**

**Fetchez** is a robust, highly modular and extensible Python framework designed to orchestrate complex geospatial data engineering workflows.

Fetchez is part of the [Continuous DEMs Project](https://continuous-dems.readthedocs.io/), an ecosystem of tools for modern, continuous digital elevation model generation.

## Key Features

* **Unified Interface**: Access [more than 100 different modules](https://fetchez.readthedocs.io/en/latest/modules/index.html) using the exact same syntax.
* **Parallel Fetching**: High-performance, multi-threaded downloading with automatic retry, timeout handling, and partial-download resumption.
* **Infrastructure as Code:** Define complex data pipelines, cropping, and gridding workflows using CLI switches or simple YAML "Recipes".
* **Pipeline Hooks**: Transparently stream, filter, and process data as it is being downloaded.
* **Infinite Extensibility:** Built on a modern plugin architecture. Drop custom Python scripts into a local folder, or install community extensions via `pip` to add your own data sources, domain schemas, processing hooks and more.

## Quickstart

**Installation:**

```bash
pip install fetchez
```

### Command Line Interface:

Fetch Copernicus topography and NOAA multibeam bathymetry for a specific bounding box in one command:

```bash
fetchez run -R loc:"Miami, FL" --global-hook audit copernicus multibeam
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
