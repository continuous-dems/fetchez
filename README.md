# Fetchez

<pre>
🐄🌍 [ F E T C H E Z ] 🌍🐄
</pre>
**The Generic Geospatial Data Acquisition and Registry Engine**

[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/ciresdem/fetchez)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![PyPI version](https://badge.fury.io/py/fetchez.svg)](https://badge.fury.io/py/fetchez)
[![project chat](https://img.shields.io/badge/zulip-join_chat-brightgreen.svg)](https://cudem.zulip.org)

**Fetchez** is a lightweight, modular and highly extendable Python library and command-line tool designed to discover and retrieve geospatial data from a wide variety of public repositories.

Originally part of the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez is now a standalone tool capable of retrieving Bathymetry, Topography, Imagery, and Oceanographic data (and more!) from sources like NOAA, USGS, NASA, and the European Space Agency.

---

## 🌎 Features

* One command to fetch data from 50+ different [modules](https://github.com/ciresdem/fetchez/blob/main/MODULES.md), (SRTM, GMRT, NOAA NOS, USGS 3DEP, Copernicus, etc.).
* Build automated data pipelines (e.g. `download -> unzip -> reproject -> log`) using built-in or custom processing hooks.
* Built-in metadata registry allows you to search for datasets by tag, agency, resolution, or license.
* Built-in "Fetchez Remote Elevation Datalist" (FRED) automatically indexes remote files for spatial querying without hitting APIs repeatedly.
* Built-in download engine with automatic retries, timeout handling, and byte-range support for resuming interrupted downloads.
* Minimal dependencies (`requests`, `tqdm`, `lxml`). Optional `shapely` support for precise spatial filtering.
* Supports user-defined Data Modules *and* Processing Hooks via `~/.fetchez/`.

---


## 📦 Installation

**From Pip/PyPi**

```bash
pip install fetchez
```

**From Source:**

Download and install git (If you have not already): [git installation](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

```bash
pip install git+https://github.com/ciresdem/fetchez.git#egg=fetchez
```

Clone and install from source

```bash
git clone https://github.com/ciresdem/fetchez.git
cd fetchez
pip install .
```

## 💻 CLI Usage

The primary command is fetchez.

### Basic Syntax

```bash
fetchez -R <region> <module> [options]
```

### Examples

 *  Fetch SRTM+ Data for a Bounding Box

```bash
# Region Format: West/East/South/North
fetchez -R -105.5/-104.5/39.5/40.5 srtm_plus
```

 * Discover Data Sources

```bash
# View detailed metadata card for a module
fetchez --info gmrt
```

 * Fetch Data Using a Place Name

```bash
# Automatically resolves "Boulder, CO" to a bounding box region
fetchez -R loc:"Boulder, CO" copernicus --datatype=1
```

 * Advanced Data Pipelines (Hooks)

```bash

# Fetch data, automatically unzip it, and print the final filepath
fetchez -R loc:Miami charts --hook unzip --pipe-path
```

 * List Available Modules

```bash
fetchez --modules
```
## 🐍 Python API

Fetchez is designed to be easily integrated into Python workflows.

### Simple Fetching

```python
import fetchez

# Define a region (West, East, South, North)
bbox = (-105.5, -104.5, 39.5, 40.5)

# Initialize a specific fetcher module
# Use the registry to load modules dynamically
SRTM = fetchez.registry.FetchezRegistry.load_module('srtm_plus')

# Configure and Run
fetcher = SRTM(src_region=bbox, verbose=True)
fetcher.run()

# Access Results (Metadata)
for result in fetcher.results:
    print(f"Downloaded: {result['dst_fn']}")
    print(f"Source URL: {result['url']}")
```

### Data Discovery

Query the registry to find datasets that match your criteria programmatically.

```python
from fetchez.registry import FetchezRegistry

# Search for global bathymetry datasets
matches = FetchezRegistry.search_modules('bathymetry')
print(f"Found modules: {matches}")

# Get details for a specific module
meta = FetchezRegistry.get_info('copernicus')
print(f"Resolution: {meta.get('resolution')}")
print(f"License: {meta.get('license')}")
```

For modules that rely on file lists (like Copernicus or NCEI), you can interact directly with the local index.
 
```python
from fetchez import fred

# Load the local index
index = fred.FRED(name='copernicus')

# Search for datasets in a region
results = index.search(
    region=(-10, 10, 40, 50),
    where=["DataType = '3'"] # Filter for COP-10 (European) data
)

print(f"Found {len(results)} datasets.")
```

## 🪝 Processing Hooks
Fetchez includes a powerful Hook System that allows you to chain actions together. Hooks run in a pipeline, meaning the output of one hook (e.g. unzipping a file) becomes the input for the next (e.g. processing it).

### Common Built-in Hooks:

 * unzip: Automatically extracts .zip files.

 * pipe: Prints the final absolute path to stdout (useful for piping to GDAL/PDAL).

### Example:

```bash

# Download data.zip
# Extract data.tif (via unzip hook)
# Print /path/to/data.tif (via pipe-path)
fetchez charts --hook unzip --hook pipe
```

You can write your own custom hooks (e.g., to log downloads to a database or trigger a script) and drop them in ~/.fetchez/hooks/. See [CONTRIBUTING.md](https://github.com/ciresdem/fetchez/blob/main/CONTRIBUTING.md) for details.

## 🗺️ Supported Data Sources

Fetchez supports over 50 modules categorized by data type. Run ```fetchez --modules``` to see the full list.

| Category | Example Modules |
|----|----|
| Topography | srtm_plus, copernicus, nasadem, tnm (USGS), arcticdem |
| Bathymetry | gmrt, emodnet, gebco, multibeam, nos_hydro |
| Oceanography |tides, buoys, mur_sst |
| Reference | osm (OpenStreetMap), vdatum |
| Generic | http (Direct URL), earthdata (NASA) |

### 🛟️ Module-Specific Dependencies

While the core `fetchez` engine is lightweight, some specialized data modules may require extra Python libraries to function (e.g., `pyshp` for TIGER data, `boto3` for AWS-based sources, or `gdal` for complex vector operations).

If you try to run a module and it complains about a missing import, check the module's help command. We document these requirements in the module's help text:

```bash
fetchez <module_name> --help
If a dependency is missing, the module will typically exit gracefully with an error message telling you exactly what to pip install.
```

## 🐄  Plugins, Hooks & Extensions

Need to fetch data from a specialized local server? Or maybe run a custom script immediately after every download? You don't need to fork the repo!

**Fetchez** is designed to be extendable in two ways:

Data Modules (~/.fetchez/plugins/): Add new data sources or APIs.

Processing Hooks (~/.fetchez/hooks/): Add new post-processing steps (unzip, convert, log).

Drop your Python scripts into these configuration folders, and they will be automatically registered as commands.

**Quick Start:**
1.  Create the folder: `mkdir ~/.fetchez/plugins`
2.  Drop a python script there (e.g., `my_data.py`).
3.  Run it: `fetchez my_data`

See [CONTRIBUTING.md](https://github.com/ciresdem/fetchez/blob/main/CONTRIBUTING.md) for a full code example.

## 🛠  Contributing

We welcome contributions! Please see [CONTRIBUTING.md](https://github.com/ciresdem/fetchez/blob/main/CONTRIBUTING.md) for details on how to register new modules or hooks with our metadata schema.

## 🔱  Disclaimer on Data Persistence

We provide the tools to locate and download data from authoritative public repositories, but we do not host the data ourselves.

Government agencies reorganize websites, migrate APIs (e.g., WCS 1.0 to 2.0), or decommission servers without notice. A module that fetches perfectly today may encounter a 404 tomorrow.

Source datasets are frequently updated, reprocessed, or removed by their custodians. The "best available" data for a region can change overnight.

Remote servers (like NOAA NCEI, USGS, or Copernicus) may experience downtime, throttling, or rate limits that are entirely outside our control.

We strive to keep our modules robust and our index fresh. If you encounter a broken fetch or a changed endpoint, please open an issue. This helps the whole community keep up with the changes!

## 📄  License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/ciresdem/fetchez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
