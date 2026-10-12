# 🪝 Hooks & Presets

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

### Understanding Hook Capabilities

Fetchez hooks are designed to be composable. Some filter entries before downloading, others modify files, create new artifacts, initialize streams, or process streamed data.

Registered hooks can advertise metadata to help you understand their capabilities and determine how they fit into a workflow.

#### What hooks do

The `effects` metadata describes the kinds of operations a hook performs.

| Effect              | Description                                                     |
|---------------------|-----------------------------------------------------------------|
| `filters-entries`   | Selects which entries continue through the pipeline.            |
| `modifies-entries`  | Updates entry metadata or properties.                           |
| `creates-entries`   | Produces additional entries, such as extracted archive members. |
| `modifies-artifact` | Changes an existing file.                                       |
| `creates-artifact`  | Produces an additional file or artifact.                        |
| `creates-stream`    | Initializes a stream for processing.                            |
| `filters-chunks`    | Filters streamed data.                                          |
| `transforms-stream` | Converts one stream representation into another.                |
| `consumes-stream`   | Reads or observes streamed chunks, possibly generating output.  |
| `consumes-file`     | Reads or observes file artifacts, possibly generating output.   |

A hook may have several effects. For example, an archive extraction hook can create new files and corresponding entries, while a provenance hook may generate supplementary artifacts.

These descriptions help identify suitable hooks but do not imply that every invocation will produce an output.

#### Data types and stream types

Fetchez distinguishes between an artifact's `data_type` and an initialized stream's `stream_type`.

- **Data type:** Describes the artifact, such as `raster`, `vector`, or `archive`.
- **Profile:** Selects how a reader interprets an entry.
- **Stream type:** Describes the representation of chunks produced by that reader, such as `raster-stream` or `point-stream`.

For example, a GeoTIFF identified as `raster` could be read as a generic windowed `raster-stream`, or interpreted by an extension as a point-stream.

Some hooks advertise `accepts` and `produces` metadata describing the stream representations they work with.

```text
Raster reader
    produces: raster-stream
         |
         v
Raster-to-points hook
    accepts: raster-stream
    produces: point-stream
         |
         v
Point filtering hook
    accepts: point-stream
```

Fetchez does not automatically convert between arbitrary stream representations. When a hook requires a different stream type, select an appropriate reader profile or insert a compatible transformation hook.

Hooks that operate only on entry metadata or files generally do not need stream-type declarations.

#### Hook requirements and related components

Some hooks depend on other hooks to complete their work. These dependencies may be declared through `requires` metadata.

For example:

```text
Requires:
  global-product-index
    Scope: global
    Stage: collection
```

This indicates that the required hook should also be included in the workflow.

A `related` component is different: it may be useful alongside the selected hook, but is not mandatory.

Declaring a requirement does not automatically insert the missing hook. Recipe validation or modifiers may provide additional dependency handling when configured.

#### Choosing a hook's stage

A hook's registered stage is its default execution point, but many hooks support stage overrides.

For example, a filename filter could run:

- At `manifest` stage to avoid downloading unwanted files.
- At `file` stage to select files created by an extraction hook.
- At `collection` stage to filter finalized entries.

Changing a hook's stage changes when it executes, not necessarily what it does. Some hooks require files or streams that are unavailable at earlier stages, so check the hook's documentation before overriding its stage.

#### Discovering hooks

Use the Hook Registry through the CLI to inspect available hooks, including those supplied by installed extensions and local plugins.

```bash
fetchez hooks list
fetchez hooks info stream-init
```

Where available, registry metadata can help identify a hook's default stage, effects, accepted stream types, produced stream types, dependencies, and related components.

Not every hook declares every field. Missing metadata should be interpreted as *not specified*, rather than proof that a hook cannot support a particular workflow.

For detailed arguments, examples, and limitations, see the [Hook Reference](hooks/index.md).

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
fetchez build charts unzip pipe

# warp the copernicus files right when they're downloaded
fetchez build -R loc:denver copernicus pipe | xargs gdalwarp -t_srs EPSG:3857

# build a vrt of the fetched files
gdalbuildvrt cop_merged.vrt $(fetchez build -R -105/-104/39/40 copernicus pipe)
```

## Hook Presets (Macros)

Presets are YAML configuration files that define a preset group of hooks. Giving you the ability to make complex hook macros.
You can make your own, or use a pre-configured Preset from fetchez or it's extensions.

Instead of running this long command:

```bash
fetchez build copernicus checksum --algo sha256 enrich audit --file log.json
```

You can define a preset and simply run:

```bash
fetchez build copernicus audit-full
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
fetchez build charts audit-full
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
