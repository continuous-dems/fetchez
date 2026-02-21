# Fetchez

**Fetch geospatial data with ease.**

*Fetchez Les Données*

**Fetchez** is a lightweight, modular and highly extendable Python library and command-line tool designed to discover, retrieve and process geospatial data from a wide variety of public repositories.

## Quickstart

**Installation:**

```bash
pip install fetchez
```

### Command Line Interface:

Fetch Copernicus topography and NOAA multibeam bathymetry for a specific bounding box in one command:

```bash
fetchez -R loc:"Miami, FL" copernicus multibeam
```

### Python API:

```python
from fetchez.core import run_fetchez
from fetchez.registry import FetchezRegistry

# Load a module dynamically
MBModule = FetchezRegistry.load_module('multibeam')

# Fetch data for a region
fetcher = MBModule(src_region=[-80.5, -80.0, 25.5, 26.0])
fetcher.run()
run_fetchez([fetcher])
```

## Key Features

* ***Unified Interface***: Access 50+ endpoints (OData, REST, THREDDS, FTP) using the exact same syntax.

* ***Smart Geospatial Cropping***: Automatically translates user bounding boxes into the specific query parameters required by each target API.

* ***Pipeline Hooks***: Transparently stream, filter, and process data (via globato and transformez) as it is being downloaded.

* ***Parallel Fetching***: High-performance, multi-threaded downloading with automatic retry, timeout handling, and partial-download resumption.

```{toctree}
:maxdepth: 2
:hidden:
:caption: User Guide:

user_guide/installation
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: Module Catalog

modules/index
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: Python API

api/core
api/registry
api/fred
```

Indices and tables
==================

* {ref}`genindex`
* {ref}`modindex`
* :ref:`search`
