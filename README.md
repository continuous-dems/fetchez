# GeoFetch

<pre>
       _..._
     .'     '.      ___
    /    .-""-\   .'_  '\
   |   /'  _   \ / / \   \    G E O F E T C H
   |  |   (_)   |  |  \  |
   \   \     /  \   \ /  /    Data Acquisition Engine
    \   '.__.'   '.__.' /
     '.       _..._   .'
       '-----'     '-'
</pre>

**The Generic Geospatial Data Acquisition Engine**

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/ciresdem/geofetch)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)

**GeoFetch** is a lightweight, modular Python library and command-line tool designed to discover and download geospatial data from a wide variety of public repositories.

Originally part of the [CUDEM](https://github.com/ciresdem/cudem) project, GeoFetch is now a standalone tool capable of retrieving Bathymetry, Topography, Imagery, and Oceanographic data from sources like NOAA, USGS, NASA, and the European Space Agency.

---

## 🚀 Features

* **Unified Interface:** One command to fetch data from 40+ different sources (SRTM, GMRT, NOAA NOS, USGS 3DEP, Copernicus, etc.).
* **Rich Data Catalog:** Built-in metadata registry allows you to search for datasets by tag, agency, resolution, or license.
* **Spatial Indexing (FRED):** Built-in "Fetches Remote Elevation Datalist" (FRED) automatically indexes remote files for spatial querying without hitting APIs repeatedly.
* **Smart Resuming:** Robust download engine with automatic retries, timeout handling, and byte-range support for resuming interrupted downloads.
* **Lightweight Core:** minimal dependencies (`requests`, `tqdm`, `lxml`). Optional `shapely` support for precise spatial filtering.

---

## 📦 Installation

**From Source:**

```bash
git clone [https://github.com/ciresdem/geofetch.git](https://github.com/ciresdem/geofetch.git)
cd geofetch
pip install .
Development Mode:Bashpip install -e .
```

## 💻 CLI Usage

The primary command is geofetch (or gfetch).Basic SyntaxBashgeofetch -R <region> <module> [options]
Examples

1. Fetch SRTM+ Data for a Bounding BoxBash# Region Format: West/East/South/North
```geofetch -R -105.5/-104.5/39.5/40.5 srtm_plus```

2. Discover Data SourcesBash# View detailed metadata card for a module
```geofetch --info gmrt```

3. Fetch Data Using a Place NameBash# Automatically resolves "Boulder, CO" to a bounding box
```geofetch -R loc:"Boulder, CO" copernicus --datatype=1```

4. List Available ModulesBashgeofetch --modules

### Common Flags

-R, --region: Set the area of interest (Bounding Box, Place Name, or File).
-l, --list: Print the URLs found but do not download them.
-H, --threads: Number of parallel download threads (default: 1).
--info: Display metadata (Agency, License, Resolution) for a module.

## 🐍 Python API

GeoFetch is designed to be easily integrated into Python workflows.

### Simple Fetching

```python
import geofetch

# 1. Define a region (West, East, South, North)
bbox = (-105.5, -104.5, 39.5, 40.5)

# 2. Initialize a specific fetcher module
# Use the registry to load modules dynamically
SRTM = geofetch.registry.GeoFetchRegistry.load_module('srtm_plus')

# 3. Configure and Run
fetcher = SRTM(src_region=bbox, verbose=True)
fetcher.run()

# 4. Access Results (Metadata)
for result in fetcher.results:
    print(f"Downloaded: {result['dst_fn']}")
    print(f"Source URL: {result['url']}")
```

### Data Discovery

Query the registry to find datasets that match your criteria programmatically.

```python
from geofetch.registry import GeoFetchRegistry

# Search for global bathymetry datasets
matches = GeoFetchRegistry.search_modules('global bathymetry')
print(f"Found modules: {matches}")

# Get details for a specific module
meta = GeoFetchRegistry.get_info('copernicus')
print(f"Resolution: {meta.get('resolution')}")
print(f"License: {meta.get('license')}")
Using FRED (Local Index)For modules that rely on file lists (like Copernicus or NCEI), you can interact directly with the local index.Pythonfrom geofetch import fred

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

GeoFetch supports over 40 modules categorized by data type. Run ```geofetch --modules``` to see the full list.

| Category | Example Modules |
|----|----|
| Topography | srtm_plus, copernicus, nasadem, tnm (USGS), arcticdem |
| Bathymetry | gmrt, emodnet, gebco, multibeam, nos_hydro |
| Oceanography |tides, buoys, mur_sst |
| Reference | osm (OpenStreetMap), vdatumGenerichttp (Direct URL), earthdata (NASA) |

## 🛠️ Contributing

We welcome contributions! Please see CONTRIBUTING.md for details on how to register new modules with our enhanced metadata schema.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.Copyright (c) 2010-2026 Regents of the University of Colorado
