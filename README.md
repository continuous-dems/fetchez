# Fetchez

<pre>
🐄🌍 [ F E T C H E Z ] 🌍🐄
</pre>
**The Generic Geospatial Data Acquisition and Registry Engine**

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](https://github.com/ciresdem/fetchez)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![PyPI version](https://badge.fury.io/py/fetchez.svg)](https://badge.fury.io/py/fetchez)
[![project chat](https://img.shields.io/badge/zulip-join_chat-brightgreen.svg)](https://cudem.zulip.org)

**Fetchez** is a lightweight, modular Python library and command-line tool designed to discover and retrieve geospatial data from a wide variety of public repositories.

Originally part of the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez is now a standalone tool capable of retrieving Bathymetry, Topography, Imagery, and Oceanographic data (and more!) from sources like NOAA, USGS, NASA, and the European Space Agency.

---

## 🌎 Features

* One command to fetch data from 40+ different sources (SRTM, GMRT, NOAA NOS, USGS 3DEP, Copernicus, etc.).
* Built-in metadata registry allows you to search for datasets by tag, agency, resolution, or license.
* Built-in "Fetchez Remote Elevation Datalist" (FRED) automatically indexes remote files for spatial querying without hitting APIs repeatedly.
* Built-in download engine with automatic retries, timeout handling, and byte-range support for resuming interrupted downloads.
* Minimal dependencies (`requests`, `tqdm`, `lxml`). Optional `shapely` support for precise spatial filtering.
* Supports user-defined plugins via `~/.fetchez/plugins/`.

---


## 📦 Installation

## From Pip/PyPi

```bash
pip install fetchez
```

Download and install git (If you have not already): [git installation](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

```bash
pip install git+https://github.com/ciresdem/fetchez.git#egg=fetchez

```

**From Source:**

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

## 🗺️ Supported Data Sources

Fetchez supports over 40 modules categorized by data type. Run ```fetchez --modules``` to see the full list.

| Category | Example Modules |
|----|----|
| Topography | srtm_plus, copernicus, nasadem, tnm (USGS), arcticdem |
| Bathymetry | gmrt, emodnet, gebco, multibeam, nos_hydro |
| Oceanography |tides, buoys, mur_sst |
| Reference | osm (OpenStreetMap), vdatum |
| Generic | http (Direct URL), earthdata (NASA) |

## 🐄 Plugins & Extensions

Need to fetch data from a specialized local server, a private S3 bucket, or a niche API? You don't need to fork the repo!

**Fetchez** supports user-defined plugins. Drop a Fetchez compatible Python script into your configuration folder, and it will be automatically registered as a command.

**Quick Start:**
1.  Create the folder: `mkdir ~/.fetchez/plugins`
2.  Drop a python script there (e.g., `my_data.py`).
3.  Run it: `fetchez my_data`

See [CONTRIBUTING.md](CONTRIBUTING.md) for a full code example.

## 🛠️ Contributing

We welcome contributions! Please see [CONTRIBUTING.md](/CONTRIBUTING.md) for details on how to register new modules with our metadata schema.

## ⚠️ Disclaimer on Data Persistence

We provide the tools to locate and download data from authoritative public repositories, but we do not host the data ourselves.

Government agencies reorganize websites, migrate APIs (e.g., WCS 1.0 to 2.0), or decommission servers without notice. A module that fetches perfectly today may encounter a 404 tomorrow.

Source datasets are frequently updated, reprocessed, or removed by their custodians. The "best available" data for a region can change overnight.

Remote servers (like NOAA NCEI, USGS, or Copernicus) may experience downtime, throttling, or rate limits that are entirely outside our control.

We strive to keep our modules robust and our index fresh. If you encounter a broken fetch or a changed endpoint, please open an issue. This helps the whole community keep up with the changes!

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
