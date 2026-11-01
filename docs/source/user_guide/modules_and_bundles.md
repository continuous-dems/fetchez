# 🌎 Modules & Bundles

Modules are Fetchez's data sources. Each one knows how to discover and retrieve a particular dataset — a government API, a cloud catalog, a REST service, or a directory on your own disk.

Fetchez ships with [more than 100 registered modules](modules/index.md) covering bathymetry, topography, imagery, lidar, nautical charts, and more. Alongside those provider-specific modules, Fetchez lets you reach new datasets **through configuration first**, without writing Python.

> **Running example:** In [Usage](usage.md) we used the `stac` module to find Copernicus DEM tiles around San Diego. This page explains what that module is, how its arguments work, and how to group modules into reusable bundles.

## Module Reference

For detailed documentation of individual modules, including configuration, examples, and limitations, see the [Module Reference](modules/index.md).

Not every registered module has a dedicated documentation page. Use the `fetchez modules` CLI commands or the `ModuleRegistry` to discover additional built-in and extension-provided modules.

```{toctree}
:maxdepth: 2

modules/index
```

## Two Kinds of Module

| Kind | What it is | When to use it |
|------|------------|----------------|
| **Provider modules** | Named modules that encode provider-specific behaviour for a known dataset | A module already exists for your dataset |
| **Generic modules** | Configurable interfaces for whole classes of service | You need a new source and don't want to write Python |

Both kinds behave identically once registered: they appear in `fetchez modules list`, accept arguments, and can be chained with hooks.

### Generic Modules

These five modules cover most "new dataset" situations without requiring new code:

| Generic module | Best for |
|----------------|----------|
| **`local_fs`** | Files, file lists, and directories already on your machine |
| [**`http_index`**](modules/http_index.md) | HTTP directory listings and web pages linking to downloadable assets, with optional FRED spatial indexing |
| [**`rest_api`**](modules/rest_api.md) | REST/JSON APIs, search responses, pagination, and discovered asset URLs |
| [**`stac`**](modules/stac.md) | Spatial and temporal asset catalogs, including imagery, elevation, lidar, and other cloud datasets |
| [**`thredds`**](modules/thredds.md) | Scientific THREDDS catalogs and services including HTTPServer, NCSS, WCS, and OPeNDAP |

### Provider Modules

Provider modules wrap a specific service and handle its quirks for you — authentication schemes, pagination conventions, product naming, and data-type defaults. Examples include `tnm` (USGS 3DEP elevation), `copernicus` (Copernicus DEM), `charts` (NOAA Electronic Nautical Charts), `nos_hydro` (NOS hydrographic surveys), and `margrav` (Marine Gravity).

Prefer a provider module when one exists. Reach for a generic module when it doesn't, and write a [custom module](../contribute/index.md) only when the source genuinely needs specialised discovery logic.

## Configuring a Module

Every module exposes its own arguments. Discover them with `--help`:

```bash
fetchez build stac --help
fetchez build tnm --help
```

Arguments follow the component they configure, so in a chain each module's flags sit directly after its name:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  tnm \
  --products 1m
```

Here `--url`, `--collections`, and `--assets` belong to `stac`, while `--products` belongs to `tnm`.

### Specifying a Region

Many modules accept a region of interest, which Fetchez passes through as `-R`. Three forms are accepted:

```bash
-R 'loc:san diego, ca'          # A named place
-R -117.3/-116.8/32.6/33.0      # West/East/South/North
-R my_location.geojson          # A vector file
```

Named-place lookup is convenient interactively; explicit bounds are preferable in recipes, where reproducibility matters more than brevity.

## Module Bundles

Bundles are YAML files that group modules — optionally with preset arguments and hooks — so a common combination can be invoked by a single name. Bundles are used anywhere a module is used, including inside other bundles.

### Defining a Bundle

Place the file in your `~/.fetchez/modules/bundles/` plugin folder:

```yaml
name: grav_and_bath
description: >
  Some fast bathymetry data sources.
modules:
  - module: margrav
    args:
      weight: .01
  - module: nos_hydro
    args:
      datatype: "xyz"
      weight: .35
    hooks:
      - name: unzip
      - name: set_datatype
        args:
          data_type: "nos_xyz"
  - module: charts
    args:
      weight: .15
    hooks:
      - name: extract
      - name: filename_filter
        args:
          match: ".000"
          stage: "file"
      - name: set_datatype
        args:
          data_type: "charts_000"
```

Note how each module carries its own `hooks` block. Those hooks apply only to that module's entries — the same scoping rule described in [Usage](usage.md), expressed in YAML.

### Running a Bundle

Your new `grav_and_bath` bundle is registered in the `BundleRegistry` and available from the CLI:

```bash
fetchez build -R 'loc:portland, me' grav_and_bath
```

### Using a Bundle in a Recipe

Bundles can also be referenced from recipes, or from other bundles:

```yaml
project:
  name: "my_harbor"

region: 'loc:portland, me'

modules:
  - bundle: grav_and_bath
    args:
      weight: 1.0
```

### Selecting Bundle Members

The `select` key narrows a bundle to specific members at runtime, using dotted paths into their existing YAML definitions:

```yaml
modules:
  - bundle: my_sources
    select:
      module:
        - copernicus
        - margrav
      args.format: GeoTIFF
```

Selection rules:

* Dotted paths such as `args.products` select against the module's existing configuration
* Multiple keys are ANDed; multiple values for one key are ORed
* Members that don't define the selected path are **kept**, so helper modules pass through unchanged
* A path that exists on no member raises an error
* Selection happens before recursive bundle expansion and default argument propagation

From the CLI:

```bash
fetchez build -R '<W/E/S/N>' tnm --select products=1m/1_9as
```

## Extending Modules and Bundles

Fetchez is generic by design. To ship your own modules or bundles as an installable extension, create a `modules` directory in your project — Python files defining modules, and/or a `modules/bundles` directory of YAML bundles — then register them in `pyproject.toml`:

**Modules**

```toml
[project.entry-points."fetchez.modules"]
my_project_modules = "my_project.modules"
```

**Bundles**

```toml
[project.entry-points."fetchez.modules.bundles"]
my_project_bundles = "my_project.modules.bundles"
```

Anything registered this way becomes discoverable through `fetchez.registry` and appears in `fetchez modules list` alongside the built-ins. For local, non-distributed work, drop the same files into `~/.fetchez/modules/` instead — see [Plugins & Extensions](plugins_and_extensions.md).

---

**Next up:** See [Hooks & Presets](hooks_and_presets.md) to learn how to process the data your modules retrieve.
