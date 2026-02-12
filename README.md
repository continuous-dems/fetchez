# 🌍 Fetchez 🐄 

**Fetch geospatial data with ease.** *Fetchez Les Données*

[![Version](https://img.shields.io/badge/version-0.4.2-blue.svg)](https://github.com/ciresdem/fetchez)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![PyPI version](https://badge.fury.io/py/fetchez.svg)](https://badge.fury.io/py/fetchez)
[![project chat](https://img.shields.io/badge/zulip-join_chat-brightgreen.svg)](https://cudem.zulip.org)

**Fetchez** is a lightweight, modular and highly extendable Python library and command-line tool designed to discover and retrieve geospatial data from a wide variety of public repositories. Originally part of the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez is now a standalone tool capable of retrieving Bathymetry, Topography, Imagery, and Oceanographic data (and more!) from sources like NOAA, USGS, NASA, and the European Space Agency.

---

### Why Fetchez?

Geospatial data access is fragmented. You often need one script to scrape a website for tide stations, another to download LiDAR from an S3 bucket, and a third to parse a local directory of shapefiles.

**Fetchez unifies this chaos.**
* **One Command to Fetch Them All:** Whether you need bathymetry, topography, or water levels, the syntax is always the same: `fetchez [module] -R [region]`.
* **Streaming First:** Fetchez is built for the cloud-native era. It prefers streaming data through standard pipes over downloading massive archives to disk.
* **Plugin Architecture:** The core engine is lightweight and agnostic. Data sources are just Python plugins, making it trivial to add support for new APIs or proprietary internal servers without forking the main codebase.
* **Smart caching:** It handles the boring stuff like retries, caching, and checksum verification, so you can get back to the science.

## Features

* One command to fetch data from 50+ different modules, (SRTM, GMRT, NOAA NOS, USGS 3DEP, Copernicus, etc.).
* Built-in download management handles retries, resume-on-failure, authentication, and mirror switching automatically.
* Seamlessly mix disparate data types (e.g., fetch Stream Gauges (JSON), DEMs (GeoTIFF), and Coastlines (Shapefile) in one project).
* Define automated workflows (Hooks) (e.g., download -> unzip -> reproject -> grid) using Python-based Processing Hooks.
* Save complex processing chains (Presets) as simple reusable flags (e.g., fetchez ... --run-through-waffles).
* Includes "FRED" (Fetchez Remote Elevation Datalist) to index and query remote or local files spatially without hitting slow APIs or maintianing a database.
* Minimal dependencies (`requests`, `tqdm`, `lxml`). Optional `shapely` support for precise spatial filtering.
* Supports user-defined Data Modules *and* Processing Hooks via `~/.fetchez/`.

---

## Where does Fetchez fit?

The geospatial ecosystem is full of powerful processing engines, translators, tansformers, converters, etc. but they all assume you already have the data ready to use. Fetchez fills the gap between the internet, your hard drive and your workflow.

In short: Use Fetchez to get the data so you can crunch the data.

## Installation

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

## CLI Usage

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
## Python API

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

## Processing Hooks
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

## Pipeline Presets (Macros)
Tired of typing the same chain of hooks every time? Presets allow you to define reusable workflow macros.

Instead of running this long command:

```bash

fetchez copernicus --hook checksum:algo=sha256 --hook enrich --hook audit:file=log.json
```

You can simply run:

```bash

fetchez copernicus --audit-full
```

*** How to use them ***

Fetchez comes with a few built-in shortcuts (check fetchez --help to see them), but the real power comes from defining your own.

* Initialize your config: Run this command to generate a starter configuration file at `~/.fetchez/presets.json`:

```bash

fetchez --init-presets
```

* Define your workflow: Edit the JSON file to create a named preset. A preset is just a list of hooks with arguments.

```json

"my-clean-workflow": {
  "help": "Unzip files and immediately remove the zip archive.",
  "hooks": [
    {"name": "unzip", "args": {"remove": "true"}},
    {"name": "pipe"}
  ]
}
```

* Run it: Your new preset automatically appears as a CLI flag!

```bash

fetchez charts --my-clean-workflow
```

## Supported Data Sources

Fetchez supports over 50 modules categorized by data type. Run ```fetchez --modules``` to see the full list.

| Category | Example Modules |
|----|----|
| Topography | srtm_plus, copernicus, nasadem, tnm (USGS), arcticdem |
| Bathymetry | gmrt, emodnet, gebco, multibeam, nos_hydro |
| Oceanography |tides, buoys, mur_sst |
| Reference | osm (OpenStreetMap), vdatum |
| Generic | http (Direct URL), earthdata (NASA) |

## Module-Specific Dependencies

Fetchez is designed to be lightweight. The core installation only includes what is strictly necessary to run the engine.

However, some data modules require extra libraries to function (e.g., `boto3` for AWS data, `pyshp` for Shapefiles). You can install these "Extras" automatically using pip:

```bash
# Install support for AWS-based modules (BlueTopo, etc.)
pip install "fetchez[aws]"

# Install support for Vector processing (Shapefiles, etc.)
pip install "fetchez[vector]"

# Install ALL optional dependencies
pip install "fetchez[full]"
```

If you try to run a module without its required dependency, fetchez will exit with a helpful error message telling you exactly which extra group to install.

## Plugins, Hooks & Extensions

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

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](https://github.com/ciresdem/fetchez/blob/main/CONTRIBUTING.md) for details on how to register new modules or hooks with our metadata schema.

## Disclaimer on Data Persistence

We provide the tools to locate and download data from authoritative public repositories, but we do not host the data ourselves.

Government agencies reorganize websites, migrate APIs (e.g., WCS 1.0 to 2.0), or decommission servers without notice. A module that fetches perfectly today may encounter a 404 tomorrow.

Source datasets are frequently updated, reprocessed, or removed by their custodians. The "best available" data for a region can change overnight.

Remote servers (like NOAA NCEI, USGS, or Copernicus) may experience downtime, throttling, or rate limits that are entirely outside our control.

We strive to keep our modules robust and our index fresh. If you encounter a broken fetch or a changed endpoint, please open an issue. This helps the whole community keep up with the changes!

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/ciresdem/fetchez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
