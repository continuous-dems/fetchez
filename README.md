<p align="center">
	<a href="https://continuous-dems.readthedocs.io">
		<img src="https://raw.githubusercontent.com/continuous-dems/fetchez/refs/heads/main/docs/source/_static/fetchez-logo.svg" height="80" alt="Fetchez Logo">
	</a>
</p>
<h1 align="center">Fetchez</h1>
<p align="center"><strong>Fetch. Cache. Deliver.</strong></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-yellow.svg" alt="Python"></a>
  <a href="https://badge.fury.io/py/fetchez"><img src="https://badge.fury.io/py/fetchez.svg" alt="PyPI version"></a>
  <a href="https://anaconda.org/conda-forge/fetchez"><img src="https://img.shields.io/conda/vn/conda-forge/fetchez.svg" alt="Conda Version"></a>
  <a href="https://cudem.zulip.org"><img src="https://img.shields.io/badge/zulip-join_chat-brightgreen.svg" alt="Project Chat"></a>
  <a href="https://doi.org/10.5281/zenodo.22130386"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.22130386.svg" alt="DOI"></a>
</p>

**Fetchez** is a robust, highly modular and extensible Python framework designed to orchestrate complex geospatial data engineering workflows.

Originally developed as the core fetching engine for the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez has evolved into a standalone geospatial ETL platform. It seamlessly retrieves Bathymetry, Topography, Imagery, and Oceanographic data from dozens of global repositories (NOAA, USGS, Copernicus, ESA) and processes it on the fly.

---

## 📦 Installation

```bash
pip install fetchez
```

**Optional Extensions:**
To enable module specific library dependencies, install with the desired extras:

```bash
pip install fetchez[full]
```

## 🐄 Quickstart
Fetch Copernicus topography and NOAA multibeam bathymetry for a specific bounding box in one command:

### CLI

```bash
fetchez run -R loc:"Miami, FL" --global-hook audit copernicus multibeam
```

Or run a full processing pipeline from a YAML recipe:

```bash
fetchez recipes run recipes/my_dem_project.yaml
```

### Python

```python
import fetchez

# Fetch Electronic Nautical Chart data from NOAA
files = fetchez.get("charts", region=[-120, -118, 33, 34], hooks=['unzip', 'filename_filter:match=.000', 'audit'])
```

### DEM Building with Globato
While **Fetchez** handles the data retrieval, data stream initiation and processing pipeline engine, its sister project and Fetchez extension, **Globato**, provides the `multi_stack` accumulators and `mr-globato` multi-resolution interpolation engines needed to turn those streams into production-grade Digital Elevation Models. [Check it out!](https://github.com/continuous-dems/globato)

---

## 📚 Documentation
Would you like to know more? Check out our [Official Documentation](https://fetchez.readthedocs.io) to learn about:

* **Modules & Bundles:** Discover and learn about [more than 100 public datasets](https://fetchez.readthedocs.io/en/latest/modules/index.html) available through Fetchez.

* **The Python API:** Build custom fetch modules and run full processing pipelines in your apps.

* **Recipes & YAML:** Build and run custom workflows from a simple YAML or JSON configuration.

* **Hooks & Presets:** Automate unzipping, filtering, and processing fetch modules.

* **Recipe Modifiers:** Catcha recipe before it runs and modify it on the fly at runtime.

* **Domain Schemas:** Enforce rigorous geospatial standards automatically.

* **Custom Plugins:** Write your own data fetch modules, processing hooks, extensions and recipes.

* **Execution Lifecycle:** Learn about the distinct phases (`manifest` -> `file` -> `stream` -> `collection`) of fetchez module hook processing.

---

## 🛠️ Used By

This project is used by the following open-source projects:

* **[globato](https://github.com/continuous-dems/globato)** - A full Fetchez extension, optimized hooks, modules, streams and more to aid in the development of DEMs.
* **[ivert](https://github.com/continuous-dems/ivert)** - The ICESat-2 Validation of Elevations Reporting Tool.
* **[transformez](https://github.com/continuous-dems/transformez)** - A standalone Python engine for converting geospatial data between vertical datums.

*Are you using this project? Open a Pull Request to add your project to the list!*

---

## ⚖ License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/continuous-dems/fetchez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
