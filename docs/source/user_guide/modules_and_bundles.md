# 🌎 Modules & Bundles

Fetchez comes builtin with [more than 100 different modules](https://fetchez.readthedocs.io/en/latest/modules/index.html) to access geospatial data from various remote apis and local file-systems.

## Module Reference

For detailed documentation of individual modules, including configuration,
examples, and limitations, see the Module Reference.

Not every registered module has a dedicated documentation page.
Use the `fetchez modules` CLI commands or the `ModuleRegistry` to discover
additional built-in and extension-provided modules.

```{toctree}
:maxdepth: 2

modules/index
```

## Data Modules

Fetchez includes a **Module System** in its `ModuleRegistry` that allows you to access various geospatial data sources locally or from around the world.

Modules come with their own arguments to set different data types, modify outputs, set credentials, etc. Hooks can be used to modify or manage modules before, during or after fetching; allowing for full ETL processing workflows using disparate sets of data modules.

Modules define a specific dataset, either a full data collection from a government API, a simple REST service that distributes daily tides or a single file located on your hard-drive.

## Module Bundles

Bundles are YAML configuration files that define a group of Modules, possibly with preset arguments and hooks and can be used in the same ways as standard modules.
You can make your own, or use a pre-configured Bundle from Fetchez or it's extensions.

### Example

**Define your bundle**

Put this in your `~/.fetchez/modules/bundles/` plugin folder

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
      - name: unzip
      - name: filename_filter
        args:
          match: ".000"
          stage: "file"
      - name: set_datatype
        args:
          data_type: "charts_000"
```

* **Run it:** Your new `grav_and_bath` bundle is now registrered in the `BundleRegistry` and available in the fetchez cli:

```bash
fetchez build -R loc:"portland, me" grav_and_bath
```

* **Add it:** You can also use the bundle as a module in `recipes` or can be referenced by other Bundles.

```yaml
project:
  name: "my_harbor"
  region: loc:"portland, me"
  modules:
  - bundle: grav_and_bath
    args: {weight: 1.0}
```

### Selecting Bundle Members
Bundles accept a `select` syntax to allow for selecting specific module entries that exist in a bundle entry. The select key accepts dotted path key-pairs for selection.

`select` filters members using values already present in their YAML definitions. Selector keys use dotted paths such as args.products. Members that do not define a selected path are retained, allowing helper modules or hooks to pass through unchanged.

* dotted paths such as args.products select against the existing module configuration
* multiple keys are ANDed
* multiple values for one key are ORed
* members without that key are kept
* an invalid path that exists on no bundle members raises an error
* selection happens before recursive bundle expansion/default argument propagation

```yaml
modules:
  - bundle: my_sources
    select:
      module:
        - copernicus
        - margrav
      args.format: GeoTIFF
```

## Extending Bunldes (Plugins and Extensions)
Fetchez is generic. If you are building a custom tool and want to create a custom module or bundle your own custom set of modules, you can register them  either in your project or in the `~.fetchez` configuration directory and they will be discoverable with the `fetchez.registry`

To create an extension where your bundles can be installed and used by `fetchez`, make a directory called 'modules' in your project; add any python source files defining the module there or make a directory called `modules/bundles` add any YAML bundle definitions there and register them with `fetchez` in your `pyproject.toml`:

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
