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
import fetchez

# Search
fetchez.search("bathymetry")

# Get Data (Returns list of local file paths)
files = fetchez.get("nos_hydro", region=[-120, -118, 33, 34], year=2020)

# Advanced (With Hooks)
files = fetchez.get("blue_topo", hooks=['unzip', 'filter:match=.tif'])
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

user_guide/index
api/index
modules/index
```

Indices and tables
==================

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
