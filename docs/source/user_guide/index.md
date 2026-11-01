# User Guide

Welcome to the Fetchez User Guide. This is your starting point for learning how to fetch, process, and compose geospatial data with Fetchez.

## What Is This Guide For?

The User Guide teaches you how to **use** Fetchez. It covers:

* Installing and setting up Fetchez on your system
* Finding and configuring data sources (modules and bundles)
* Building pipelines with processing hooks and presets
* Creating reusable, reproducible workflows with recipes
* Streaming data with readers and streams
* Using both the command-line interface and Python API

If you want to **extend** Fetchez by writing custom modules, hooks, or readers, see the [Contributor Guide](../contribute/index.md) instead.

## How to Read This Guide

### New to Fetchez? Follow the Flow

For most users, reading in order provides the clearest learning path:

| Order | Page | What You'll Learn |
|-------|------|-------------------|
| 1 | [Installation](installation.md) | Install Fetchez and optional data providers |
| 2 | [Usage](usage.md) | Build and run pipelines from the command line |
| 3 | [Modules & Bundles](modules_and_bundles.md) | Discover and configure data sources |
| 4 | [Hooks & Presets](hooks_and_presets.md) | Add processing steps to your pipelines |
| 5 | [Streams & Readers](streams.md) | Stream and decode data for programmatic use |
| 6 | [Recipes](recipes.md) | Save, share, and replay complete workflows |

Each page builds on the previous one. If you get stuck, check the [Command Line Interface](cli_usage.md) for reference syntax or the [API Reference](../api/index.md) for Python usage.

### Want Specific Commands or Functions?

Jump directly to the reference material:

* **[Command Line Interface](cli_usage.md)** — All CLI commands, flags, and options
* **[API Reference](../api/index.md)** — Complete Python API documentation

### Building on Fetchez in Your Application?

If you're integrating Fetchez into another project or building an extension:

* **[Plugins & Extensions](plugins_and_extensions.md)** — Register local plugins or create distributable extensions
* **[Contributor Guide](../contribute/index.md)** — Contribute upstream or develop custom modules, hooks, and readers

### Working with Large or Domain-Specific Datasets?

* **[Data Persistence](data_persistence.md)** — Important notes about data reliability and source stability

---

## Running Example

Throughout this guide, we'll reference a common example workflow:

> **Goal:** Fetch Copernicus DEM data for San Diego from a STAC catalog, audit the downloads, and export as a reusable recipe.

You'll see variations of this pattern as we introduce modules, hooks, and recipes. It demonstrates the typical flow from discovery to production-ready workflow.

---

```{toctree}
:maxdepth: 2

installation
usage
cli_usage
modules_and_bundles
hooks_and_presets
streams
recipes
plugins_and_extensions
data_persistence
```

## Indices and Tables

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
