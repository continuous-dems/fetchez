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

**Fetchez** is a modular and extensible geospatial data engineering framework for discovering, retrieving, caching, transforming, and composing spatial data workflows.

Originally developed as the core fetching engine for the [CUDEM](https://github.com/ciresdem/cudem) project, Fetchez has evolved into a standalone geospatial ETL and workflow platform. Registered data Modules, Bundles, processing Hooks, Presets, recipe Modifiers, and Schemas can be composed through Python, YAML recipes, or the registry-driven command-line interface.

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

Compose and run an ad-hoc geospatial pipeline directly from registered Fetchez components.

### CLI

Fetch Copernicus topography and NOAA multibeam bathymetry for Miami and apply a global audit hook:

```bash
fetchez build -R loc:"Miami, FL" audit copernicus multibeam
```

Components are chained from left to right. Hooks and presets before the first data source are global; hooks and presets following a module or bundle apply only to that source.

For example, apply raster processing only to Copernicus while auditing the complete workflow:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    audit \
    copernicus raster_warp --res 1s \
    multibeam
```

Registered bundles can also be filtered directly from the CLI:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    glob-tnm --select products=1m/1_9as
```

Export an ad-hoc pipeline as a reusable YAML recipe:

```bash
fetchez build \
    -R loc:"Miami, FL" \
    --export miami.yaml \
    audit copernicus multibeam
```

Run the saved recipe later:

```bash
fetchez run miami.yaml
```

Use `fetchez modules list`, `fetchez modules bundles list`, `fetchez hooks list`, and `fetchez hooks presets list` to discover available components.

### Python

```python
import fetchez

# Fetch Electronic Nautical Chart data from NOAA
files = fetchez.get("charts", region=[-120, -118, 33, 34], hooks=['unzip', 'filename_filter:match=.000', 'audit'])
```

### DEM Building with Globato

Fetchez provides the generic discovery, retrieval, streaming, processing, recipe, and execution framework. Its sister project and Fetchez extension, **Globato**, adds the elevation-source vocabulary, DEM-oriented presets, MultiStack accumulation, and multi-resolution interpolation workflows used to build reproducible coastal and topobathymetric DEMs.

Globato reuses the Fetchez pipeline model while exposing a curated DEM-focused command-line interface.

[Check out Globato](https://github.com/continuous-dems/globato).

---

## 📚 Documentation

Would you like to know more? Check out our [Official Documentation](https://fetchez.readthedocs.io) to learn about:

* **Modules & Bundles:** Discover more than [more than 100 public geospatial data sources](https://fetchez.readthedocs.io/en/latest/modules/index.html) and compose curated source collections.

* **Pipeline Building:** Build ad-hoc workflows directly from registered Modules, Bundles, Hooks, and Presets with `fetchez build`.

* **Recipes & YAML:** Save, share, reproduce, and execute complete workflows with `fetchez run`.

* **Hooks & Presets:** Stream, filter, transform, inspect, and process data throughout the Fetchez execution lifecycle.

* **Bundle Selection:** Select subsets of reusable data bundles using declarative configuration fields from YAML or the CLI.

* **Recipe Modifiers:** Mutate assembled recipes before execution to apply workflow-level policy or conditional composition.

* **Domain Schemas:** Validate recipes against reusable domain-specific requirements.

* **Python API:** Search for components, retrieve data, and construct processing workflows directly from Python.

* **Plugins & Extensions:** Add custom Modules, Hooks, Readers, Streams, Bundles, Presets, Schemas, and domain-specific extensions without modifying Fetchez core.

* **Execution Lifecycle:** Learn how Fetchez moves data through manifest, file, stream, and collection processing stages.

---

## 🛠️ Used By

This project is used by the following open-source projects:

* **[Globato](https://github.com/continuous-dems/globato)** — A Fetchez extension for reproducible coastal and topobathymetric DEM construction using curated elevation sources, MultiStack accumulation, and multi-resolution interpolation workflows.
* **[IVERT](https://github.com/continuous-dems/ivert)** — The ICESat-2 Validation of Elevations Reporting Tool.
* **[Transformez](https://github.com/continuous-dems/transformez)** — A geospatial reference transformation framework for vertical and spatial datum workflows, with Fetchez integration.

*Are you using this project? Open a Pull Request to add your project to the list!*

---

## ⚖ License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/continuous-dems/fetchez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
