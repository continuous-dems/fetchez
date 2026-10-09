# 🪝 Hooks

Fetchez is designed to be highly extendable. Using **hooks** and **presets**, you can build automated pipelines that process fetched or local data on the fly.

## Hook Reference

For detailed documentation of individual hooks, including configuration,
examples, and limitations, see the [Hook Reference](hooks/index.md).

Not every registered hook has a dedicated documentation page.
Use the `fetchez hooks` CLI commands or the `HookRegistry` to discover
additional built-in and extension-provided hooks.

```{toctree}
:maxdepth: 2

hooks/index
```

## Processing Hooks

Fetchez includes a **Hook System** in its `HookRegistry` that allows you to chain actions together. Hooks run in a pipeline, meaning the output of one hook (e.g., unzipping a file) becomes the input for the next (e.g., streaming and processing it). Hooks can also manipulate or aggregate the fetched data's metadata, trigger outside software or just pass the data in a new direction or make attached artifacts.

There are four stages in the Hook lifecycle:
1. **PRE/MANIFEST Stage:** (`pre` stage) Runs before any data is downloaded (e.g., filtering URLs, masking regions).
2. **FILE Stage:** Runs on each individual file as it is downloaded (e.g., unzipping, converting formats, or piping to stdout).
3. **STREAM Stage:** Runs after the file stage where we can stream the fetched data through `readers`. (e.g. processing chunked data streams).
4. **POST/COLLECTION Stage:** (`post` stage) Runs after all files are downloaded (e.g., merging grids, calculating checksums).

Each hook defines it's default `stage`, which can be changed at any time (though won't always work as expected outside of their desred stage, so be careful changing them).

### Common Built-in Hooks:
* `unzip`: Automatically extracts `.zip` or `.gz` files.
* `pipe`: Prints the final absolute path to stdout (useful for piping to GDAL/PDAL).
* `audit`: Generates a JSON manifest of everything downloaded and processed.
* `exec`: Run a shell command on a file (uses "{file}" formatter).
* `stream-init`: Initialize a data stream and attach to the data entry.
* `copy-artifact`: Copy a data entry artifact from one location to another.
* `focus`: Focus the pipeline on a specific artifact.

### Example (CLI):
```bash
# Download data.zip
# Extract data.tif (via unzip hook)
# Print /path/to/data.tif (via pipe hook)
fetchez run charts --hook unzip --hook pipe

# warp the copernicus files right when they're downloaded
fetchez run -R loc:denver copernicus --pipe | xargs gdalwarp -t_srs EPSG:3857

# build a vrt of the fetched files
gdalbuildvrt cop_merged.vrt $(fetchez run -R -105/-104/39/40 copernicus --pipe)
```

## Hook Presets (Macros)

Presets are YAML configuration files that define a preset group of hooks. Giving you the ability to make complex hook macros.
You can make your own, or use a pre-configured Preset from fetchez or it's extensions.

Instead of running this long command:

```bash
fetchez run copernicus --hook checksum:algo=sha256 --hook enrich --hook audit:file=log.json
```

You can define a preset and simply run:

```bash
fetchez run copernicus --hook --audit-full
```

### How to create a Preset:
Presets are simply YAML files that live in your ~/.fetchez/hooks/presets/ directory or are provided as an extension or by the community. Fetchez automatically scans this folder and the `PresetRegistry` and turns any valid YAML file into a valid hook.

1. Create a file: ~/.fetchez/hooks/presets/audit_full.yaml
2. Define your workflow:

```yaml
name: audit-full
description: Generate SHA256 hashes, enrichment, and a full JSON audit logs.
hooks:
  - name: checksum
    args:
      algo: sha256
  - name: enrich
  - name: audit
    args:
      file: audit_full.json
```

**Run it:** Your new preset automatically appears in the `fetchez` `PresetRegistry` as a valid hook!

```bash
fetchez run charts --hook audit-full
```

**Add it:** You can also use the new preset in `recipes` or referenced by other `presets` and change hook arguments.

```yaml
modules:
  - module: charts
    args:
      - outdir: "%tile_dir%"
global_hooks:
  - preset: audit-full
    args:
      - name: audit
        args:
          file: charts_audit_full.json
```

### Selecting Hooks from a Preset
Presets accept a `select` syntax to allow for selecting specific hooks that exist in a preset entry. The select key accepts dotted path key-pairs for selection. Selection allows for the use of only the members of a preset that match specified existing values.

`select` filters members using values already present in their YAML definitions. Selector keys use dotted paths such as args.products. Members that do not define a selected path are retained, allowing helper modules or hooks to pass through unchanged.

* dotted paths such as args.products select against the existing module configuration
* multiple keys are ANDed
* multiple values for one key are ORed
* members without that key are kept
* an invalid path that exists on no bundle members raises an error
* selection happens before recursive bundle expansion/default argument propagation

```yaml
global_hooks:
  - preset: audit-full
    select:
      name:
        - checksum
        - audit
```

## Extending Hooks and Presets (Plugins and Extensions)
Fetchez is generic. If you are building a custom tool and want to create your own processing hooks and presets, you can register your own hooks and presets either in your project or in the `.fetchez` configuration directory and they will be discoverable with the `fetchez.registry`

In your project, make a directory called 'hooks' and/or 'hooks/presets'; add any python source hooks and YAML presets to the appropriate directory and register them with Fetchez in your `pyproject.toml`:

**Hooks**

```toml
[project.entry-points."fetchez.hooks"]
my_project_hooks = "my_project.hooks"
```

**Presets**

```toml
[project.entry-points."fetchez.hooks.presets"]
my_project_presetes = "my_project.hooks.presets"
```
