# 🌍 Fetchez 🐄

**Fetch geospatial data with ease.**

*Fetchez Les Données*

[![Version](https://img.shields.io/badge/version-0.4.2-blue.svg)](https://github.com/continuous-dems/fetchez)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![PyPI version](https://badge.fury.io/py/fetchez.svg)](https://badge.fury.io/py/fetchez)
[![project chat](https://img.shields.io/badge/zulip-join_chat-brightgreen.svg)](https://cudem.zulip.org)

**Fetchez** is a lightweight, modular and highly extendable Python library and command-line tool designed to discover and retrieve geospatial data from a wide variety of public repositories. Originally part of the [CUDEM](https://github.com/continuous-dems/cudem) project, Fetchez is now a standalone tool capable of retrieving Bathymetry, Topography, Imagery, and Oceanographic data (and more!) from sources like NOAA, USGS, NASA, and the European Space Agency.

---

```mermaid
flowchart LR
    %% Custom Styling
    classDef input fill:#2c3e50,stroke:#ecf0f1,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef engine fill:#e67e22,stroke:#ecf0f1,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef module fill:#2980b9,stroke:#ecf0f1,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef hook fill:#27ae60,stroke:#ecf0f1,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef output fill:#8e44ad,stroke:#ecf0f1,stroke-width:2px,color:#fff,rx:5px,ry:5px;

    subgraph Inputs ["Invocation"]
        direction LR
        CLI("CLI Command"):::input
        Recipe("YAML Recipe"):::input
        API("Python API"):::input
    end

    subgraph Schemas ["Apply Schemas"]
        direction LR
        Schema{"Schema Rules<br/>(Buffer, Res)"}:::engine
        Presets{"Preset Macros<br/>(--audit-full)"}:::engine
    end

    subgraph Sources ["Data Modules"]
        direction LR
        Remote[("Remote APIs<br/>(USGS, NOAA)")]:::module
        Local[("Local Files<br/>(GeoTIFF, XYZ)")]:::module
		Tools[("Dataset Generation<br/>(Coastlines, SDB)")]:::module

		Local --> Tools
        Remote --> Tools
    end


    subgraph Pipeline ["Hook Assembly Line"]
        direction LR
        Pre("PRE<br/>(Filter, Mask)"):::engine
        File(("FILE LOOP<br/>(Fetch, Unzip, Pipe)")):::engine
        Post("POST<br/>(Grid, Crop, Log)"):::engine

        Pre-->File
        File-->Post
    end

    subgraph Out ["Final Delivery"]
        direction LR
        Files("Fetched files"):::output
        Products("Derived Products"):::output
        Pipes("Pipes to the outside world"):::output
    end

    subgraph Hooks ["Hooks"]
        direction LR
        ModuleLevelHooks(("Module Level Hooks")):::hook
        GlobalLevelHooks(("Global Level Hooks")):::hook
        ModuleLevelHooks-->GlobalLevelHooks
    end

    %% Connections
    CLI --> Sources
    CLI --> Schemas
    API --> Sources
    Recipe --> Schemas
    API --> Schemas
    Schemas --> Sources
    Sources --> Pipeline
	Sources --> Out
    Pre <--> Hooks
    Pre --> Out
    File <--> Hooks
    File --> Out
    Post <--> Hooks
    Post --> Out
```

---

### ❓ Why Fetchez?

Geospatial data access is fragmented. You often need one script to scrape a website for tide stations, another to download LiDAR from an S3 bucket, and a third to parse a local directory of shapefiles.

**Fetchez unifies this chaos.**
* **One Command to Fetch Them All:** The syntax is always the same: `fetchez [module] -R [region]`.
* **Streaming First:** Fetchez prefers streaming data through standard pipes over downloading massive archives to disk.
* **Infrastructure as Code:** Define complex data pipelines, cropping, and gridding workflows using CLI switches or simple YAML "Recipes".

## 🌎 Features

* One command to fetch data from [50+ different modules](https://fetchez.readthedocs.io/en/latest/modules/index.html), (SRTM, GMRT, NOAA NOS, USGS 3DEP, Copernicus, etc.).
* Built-in download management handles retries, resume-on-failure, authentication, and mirror switching automatically.
* Seamlessly mix disparate data types (e.g., fetch Stream Gauges (JSON), DEMs (GeoTIFF), and Coastlines (Shapefile) in one command).
* Define automated workflows (Hooks) (e.g., download -> unzip -> reproject -> grid) using Python-based Processing Hooks.
* Save complex processing chains (Presets) as simple reusable flags (e.g., fetchez ... --run-through-waffles).
* Supports user-defined Data Modules *and* Processing Hooks via `~/.fetchez/`.

---

## 📦 Installation

```bash
pip install fetchez
```

## 🚀 Quickstart
Fetch Copernicus topography and NOAA multibeam bathymetry for a specific bounding box in one command:

```bash
fetchez -R loc:"Miami, FL" copernicus multibeam --audit-log miami_audit.json
```

Or run a full processing pipeline from a YAML recipe:

```bash
fetchez recipes/my_dem_project.yaml
```

---

## 📚 Documentation
Ready to do more? Check out our [Official Documentation](https://fetchez.readthedocs.io) to learn about:

* **The Python API:** Build custom fetchers into your apps.

* **Recipes & YAML:** Run custom workflows from a simple YAML configuration.

* **Hooks & Presets:** Automate unzipping, filtering, and processing.

* **Domain Schemas:** Enforce rigorous geospatial standards automatically.

* **Custom Plugins:** Write your own data fetchers.

---

## ⚖ License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/continuous-dems/fetchez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
