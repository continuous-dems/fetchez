# 📦 Installation

This guide covers installing Fetchez and the optional dependencies needed for specific data providers.

## Quick Install

The fastest way to get started:

```bash
pip install fetchez
```

This installs the core Fetchez engine with support for local files and generic data sources.

## Recommended: Conda-Forge

For users who prefer conda or need better dependency resolution for scientific packages:

```bash
conda install -c conda-forge fetchez
```

Conda is particularly useful if you plan to work with GDAL, PROJ, or other geospatial libraries that are commonly used with Fetchez modules.

## Optional Provider Dependencies

Fetchez is designed to be lightweight. The core installation only includes what's strictly necessary to run the engine. However, some data modules require extra libraries to function:

| Extra Group    | Includes            | Use Case                                         |
|----------------|---------------------|--------------------------------------------------|
| `[aws]`        | `boto3`, etc.       | AWS-based modules (BlueTopo, Earth Search, etc.) |
| `[copernicus]` | `copernicus_marine` | Copernicus Marine and SDB data                   |
| `[full]`       | All extras          | Everything above plus all optional dependencies  |

Install extras with pip:

```bash
pip install "fetchez[aws]"       # For AWS modules
pip install "fetchez[full]"      # For all provider support
```

> **Tip:** If you try to run a module without its required dependency, Fetchez will exit with a helpful error message telling you exactly which extra group or pip package to install.

## Installing External Tools

Some workflows require external command-line tools. These are **not** installed by pip/conda and must be installed separately:

| Tool | Used By | Install Command |
|------|---------|-----------------|
| **GDAL** | Raster processing hooks (`raster_warp`, `pipe`, etc.) | `conda install -c conda-forge gdal` or `apt-get install gdal-bin` |
| **PDAL** | Point cloud processing | `conda install -c conda-forge pdal` |
| **Git** | Source installations | See [git-scm.com](https://git-scm.com/) |

## Installing from Source

If you want to contribute to Fetchez or use the latest development version:

### Option 1: Install directly from Git

```bash
pip install git+https://github.com/continuous-dems/fetchez.git#egg=fetchez
```

### Option 2: Clone and install editable

```bash
git clone https://github.com/continuous-dems/fetchez.git
cd fetchez
pip install -e ".[full]"  # Include optional dependencies during dev
```

This sets up an editable installation where changes to the source code are immediately reflected without reinstalling.

## Verifying Your Installation

Test that Fetchez is working correctly:

```bash
fetchez --version
fetchez modules list
fetchez hooks list
```

If these commands execute without errors, you're ready to start fetching data.

---

**Next step:** Head to [Usage](usage.md) to learn how to build and run your first Fetchez pipeline.
