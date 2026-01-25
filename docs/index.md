---
title: The Generic Geospatial Data Acquisition Engine
---

<link rel="stylesheet" href="style.css" />

<pre>
       _..._
     .'     '.      ___
    /    .-""-\   .'_  '\
   |   /'  _   \ / / \   \    [ G E O F E T C H ]
   |  |   (_)   |  |  \  |
   \   \     /  \   \ /  /    Data Acquisition and Registry Engine
    \   '.__.'   '.__.' /
     '.       _..._   .'
       '-----'     '-'
</pre>

# GeoFetch

**The Generic Geospatial Data Acquisition and Registry Engine**

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/ciresdem/geofetch)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/ciresdem/geofetch/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)

GeoFetch is a lightweight, open-source command-line tool and Python library designed to discover and download geospatial data from a wide variety of public repositories. 

It unifies over **40 different data sources**—from NASA, USGS, NOAA, and ESA—into a single, standard interface.

* [View on GitHub](https://github.com/ciresdem/geofetch)
* [View Modules](https://github.com/ciresdem/geofetch/tree/main/src/geofetch/modules)

---

## 🌎 Why GeoFetch?

Fetching elevation, bathymetry, or oceanographic data usually involves navigating dozens of different APIs, FTP sites, and web portals. GeoFetch solves this by providing:

* One syntax to rule them all. No more memorizing `curl` flags or API endpoints.
* Our local spatial index (FRED) lets you query file-based repositories (like NCEI or Copernicus) instantly without hammering remote servers.
* Built-in connection pooling and byte-range support ensure large downloads survive flaky internet connections.

---

## 📦 Installation

GeoFetch is a standard Python package. You can install it directly from the source:

```bash
git clone [https://github.com/ciresdem/geofetch.git](https://github.com/ciresdem/geofetch.git)
cd geofetch
pip install .
```

## 💻 Usage

The core philosophy is simple: Define a Region, Pick a Module.
### The Basics

Fetch SRTM+ topography for a specific bounding box (West, East, South, North):

``` bash
geofetch -R -105.5/-104.5/39.5/40.5 srtm_plus
```

### Search by Place Name

Don't know the coordinates? Use a place name:

```bash
geofetch -R loc:"Boulder, CO" copernicus --datatype=1
```

### Discover Data

Not sure what dataset you need? Browse the registry:
```bash
# List all available modules
geofetch --modules

# View detailed metadata for a specific module
geofetch --info gmrt

# Search for all USGS data
geofetch --search usgs
```

## 🗺️ Supported Data

We support a growing federation of data sources:

| Category | Example Modules |
|----|----|
| Topography | srtm_plus, copernicus, nasadem, tnm (USGS), arcticdem |
| Bathymetry | gmrt, emodnet, gebco, multibeam, nos_hydro |
| Oceanography |tides, buoys, mur_sst |
| Reference | osm (OpenStreetMap), vdatumGenerichttp (Direct URL), earthdata (NASA) |

## 🤝 Contribute new GeoFetch Modules!

The power of GeoFetch lies in its registry. The more modules we have, the more powerful the tool becomes for the entire geospatial community.

**Do you have a favorite public dataset?** Don't keep the script to yourself—turn it into a GeoFetch module!

### How to Contribute

Adding a module is easy:

1. Create a Class: Inherit from geofetch.core.FetchModule.

2. Implement run(): Define how to translate a region into a URLs suitable to download.

3. Register It: Add your metadata (Agency, Resolution, License) to registry.py.

We have a comprehensive guide to help you get started:

Read the [Contribution Guide](https://github.com/ciresdem/geofetch/blob/main/CONTRIBUTING.md)

### License

GeoFetch is open-source software licensed under the MIT License.

Copyright (c) 2010-2026 Regents of the University of Colorado.