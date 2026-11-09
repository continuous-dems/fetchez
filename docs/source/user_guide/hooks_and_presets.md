# 🪝 Hooks & Presets

Hooks are Fetchez's processing layer. They intercept entries as they move through a pipeline — before download, during it, after it, or while data is being streamed — and inspect, filter, transform, or route what they find.

Because hooks compose, a handful of small ones can express a fairly involved ETL workflow. Presets then package a recurring chain of hooks behind a single name.

> **Running example:** In [Usage](usage.md) we attached `unzip` and `exec` to a `stac` fetch of San Diego DEM tiles, with `audit` watching the whole run. This page explains the lifecycle those hooks ran in, how to scope them, and how to bundle them into presets.

## Hook Reference

For detailed documentation of individual hooks, including configuration, examples, and limitations, see the [Hook Reference](hooks/index.md).

Not every registered hook has a dedicated documentation page. Use the `fetchez hooks` CLI commands or the `HookRegistry` to discover additional built-in and extension-provided hooks.

```{toctree}
:maxdepth: 2

hooks/index
```

## The Hook Lifecycle

Hooks run in five stages, in this order:

| Stage | Name                    | Runs                                                     | Typical use                                                             |
|-------|-------------------------|----------------------------------------------------------|-------------------------------------------------------------------------|
| 1     | **MANIFEST** (`pre`)    | Before any data is downloaded                            | Filter URLs by regex, mask regions, cap file counts, inject auth tokens |
| 2     | **FILE**                | On each file as it is downloaded                         | Unzip archives, verify checksums, convert formats, pipe paths to stdout |
| 3     | **STREAM**              | After the file stage, once `stream-init` has run         | Process chunked data through readers                                    |
| 4     | **COLLECTION** (`post`) | After all files are downloaded                           | Merge grids, calculate checksums, write audit manifests                 |
| 5     | **FINALIZE**            | Inspect, validate, report, and publish completed outputs | Generate Reports, send notifications                                    |


Each hook declares a default stage, which can be overridden. Overrides don't always behave as expected outside a hook's intended stage — a hook that needs a downloaded file cannot usefully run at `manifest` — so check the hook's documentation before changing it.

Finalize hooks run after module-level and global collection processing has completed. They receive the resulting entries and their associated artifacts, making them suitable for reporting, final validation, catalog generation, publication, and notifications.

Finalizers are ordinary Fetchez hooks and may update entries or attach additional artifacts. They do not replace teardown(), which remains responsible for releasing resources even when processing fails.

## Understanding Pipeline Entries

The common thread connecting Fetchez's modules, hooks, and readers is the **entry**. An entry is a lightweight Python dictionary representing a discovered dataset, its local file, and any metadata or artifacts associated with it.

When a module discovers a dataset, it creates an entry containing information such as:

```python
entry = {
    "url": "https://example.org/dem.tif",
    "dst_fn": "dem.tif",
    "data_type": "raster",
    "metadata": {
        "title": "Example elevation dataset",
    },
    "artifacts": {},
}
```

As the pipeline executes, the same entry carries information between processing stages:

- **Modules** discover datasets and create entries.
- **Manifest hooks** inspect, filter, or modify entries before downloading.
- **Fetching** retrieves files and updates their local state.
- **File hooks** inspect or transform downloaded files, potentially registering new artifacts.
- **Readers and stream hooks** decode data and process it incrementally.
- **Collection hooks** operate on the completed set of entries and their outputs.
- **Finalize hooks** operate on the final set of entries returned from teh Collection stage.

For example, the `exec` hook introduced in [Usage](usage.md) can run `gdal_translate` on a downloaded raster and register the resulting GeoTIFF under `entry["artifacts"]`. With `update_entry` enabled, the entry's `dst_fn` also points to the processed file, allowing subsequent hooks to work with the result.

Internally, hooks commonly receive entries as `(module, entry)` pairs and return the updated collection. This allows hooks to access both the individual dataset and its originating module's configuration.

Entries remain ordinary dictionaries by design, making them easy for extensions to inspect and enrich without requiring changes to Fetchez's core.

For the complete entry vocabulary, artifact conventions, validation helpers, and dataset identity handling, see the [Pipeline Entries](../contribute/entry.md) reference.

## Scoping Hooks

Scope is determined by **position**, not by flags. The rule is the same one introduced in [Usage](usage.md):

* Hooks before the first source are **global** and see the combined pool of data from every module
* Hooks after a module or bundle apply to **that source only**, until the next source begins

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  audit \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  unzip \
  exec --cmd "gdal_translate {file} {output}" --suffix "_compressed"
```

`audit` sits before `stac`, so it observes everything. `unzip` and `exec` sit after `stac`, so they act only on the DEM tiles.

The equivalent scoping in YAML uses `global_hooks` versus a module's own `hooks` block — see [Recipes](recipes.md).

Hooks may also be supplied with `--hook` and `--global-hook` when you need concise or backward-compatible command construction.

## Common Built-in Hooks

* `extract` — Extract `.zip` or `.gz` files
* `pipe` — Print the final absolute path to stdout (useful for piping into GDAL/PDAL, etc)
* `audit` — Generate a JSON manifest of everything downloaded and processed
* `exec` — Run a command on a file, using `{file}` and `{output}` placeholders
* `stream-init` — Initialize a data stream and attach it to the entry
* `copy-artifact` — Copy an entry's artifact from one location to another
* `focus` — Narrow the pipeline to a specific artifact

### CLI Examples

```bash
# Download data.zip, extract data.tif, print /path/to/data.tif
fetchez build charts unzip pipe

# Warp Copernicus files as they arrive
fetchez build -R 'loc:denver' copernicus pipe | xargs gdalwarp -t_srs EPSG:3857

# Build a VRT from the fetched files
gdalbuildvrt cop_merged.vrt $(fetchez build -R -105/-104/39/40 copernicus pipe)
```

## Understanding Hook Capabilities

Registered hooks advertise metadata describing what they do, which helps you judge whether a hook fits a workflow before running it.

### Effects

The `effects` field describes the kinds of operations a hook performs.

| Effect | Description |
|--------|-------------|
| `filters-entries` | Selects which entries continue through the pipeline |
| `modifies-entries` | Updates entry metadata or properties |
| `creates-entries` | Produces additional entries, such as extracted archive members |
| `modifies-artifact` | Changes an existing file |
| `consumes-entries` | Consumes or observes entries |
| `creates-artifact` | Produces an additional file or artifact |
| `consumes-artifact` | Reads or observes file artifacts, possibly generating output |
| `creates-stream` | Initializes a stream for processing |
| `filters-chunks` | Filters streamed data |
| `transforms-stream` | Converts one stream representation into another |
| `consumes-stream` | Reads or observes streamed chunks, possibly generating output |

A hook may declare several effects. An archive-extraction hook, for instance, both creates files and creates the corresponding entries. These descriptions identify suitable hooks; they don't guarantee that every invocation produces output.

### Data Types and Stream Types

Fetchez distinguishes an artifact's `data_type` from an initialized stream's `stream_type`:

* **Data type** — describes the artifact, such as `raster`, `vector`, or `archive`
* **Profile** — selects how a reader interprets an entry
* **Stream type** — describes the chunks the reader produces, such as `raster-stream` or `point-stream`

A GeoTIFF identified as `raster` might be read as a generic windowed `raster-stream`, or interpreted by an extension as a `point-stream`. Some hooks advertise `accepts` and `produces` metadata describing which representations they handle:

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

Fetchez does not convert between arbitrary stream representations automatically. When a hook needs a different stream type, select an appropriate reader profile or insert a compatible transformation hook. Hooks that only touch entry metadata or files generally need no stream-type declarations.

### Requirements and Related Components

Some hooks depend on other hooks to do their work, declared through `requires` metadata:

```text
Requires:
  global-product-index
    Scope: global
    Stage: collection
```

A `related` component is weaker: useful alongside the selected hook, but not mandatory. Declaring a requirement does **not** automatically insert the missing hook — recipe validation or modifiers may handle that when configured.

### Choosing a Stage

A hook's registered stage is its default, and many hooks support overrides. A filename filter, for example, could run:

* At `manifest` stage, to avoid downloading unwanted files
* At `file` stage, to select files produced by an extraction hook
* At `finalize` stage, to filter finalised entries

Changing a hook's stage changes *when* it runs, not necessarily *what* it does.

### Discovering Hooks

```bash
fetchez hooks list
fetchez hooks info stream-init
```

Registry metadata can reveal a hook's default stage, effects, accepted and produced stream types, dependencies, and related components. Not every hook declares every field — treat missing metadata as *not specified* rather than as proof a hook can't support a given workflow.

## Hook Presets (Macros)

Presets are YAML files defining a reusable group of hooks — essentially macros for the processing layer.

Instead of this:

```bash
fetchez build copernicus checksum --algo sha256 enrich audit --file log.json
```

you define a preset and run:

```bash
fetchez build copernicus audit-full
```

### Creating a Preset

Presets live in `~/.fetchez/hooks/presets/`, or are supplied by an extension or the community. Fetchez scans the folder and registers any valid YAML file through the `PresetRegistry`.

Create `~/.fetchez/hooks/presets/audit_full.yaml`:

```yaml
name: audit-full
description: Generate SHA256 hashes, enrichment, and full JSON audit logs.
hooks:
  - name: checksum
    args:
      algo: sha256
  - name: enrich
  - name: audit
    args:
      file: audit_full.json
```

Your preset now appears in the `PresetRegistry` as a usable hook:

```bash
fetchez build charts audit-full
```

### Using a Preset in a Recipe

Presets can be referenced from recipes, and individual hook arguments overridden by name:

```yaml
modules:
  - module: charts
    args:
      outdir: "%tile_dir%"

global_hooks:
  - preset: audit-full
    args:
      audit:
        file: charts_audit_full.json
```

### Selecting Hooks from a Preset

Like bundles, presets accept a `select` key that narrows the preset to specific members using dotted paths into their existing definitions:

```yaml
global_hooks:
  - preset: audit-full
    select:
      name:
        - checksum
        - audit
```

Selection rules:

* Dotted paths such as `args.algo` select against the hook's existing configuration
* Multiple keys are ANDed; multiple values for one key are ORed
* Members that don't define the selected path are **kept**, so helper hooks pass through unchanged
* A path that exists on no member raises an error
* Selection happens before recursive preset expansion and default argument propagation

## Extending Hooks and Presets

To ship your own hooks and presets as an installable extension, create a `hooks` directory (and optionally `hooks/presets`) in your project, then register them in `pyproject.toml`:

**Hooks**

```toml
[project.entry-points."fetchez.hooks"]
my_project_hooks = "my_project.hooks"
```

**Presets**

```toml
[project.entry-points."fetchez.hooks.presets"]
my_project_presets = "my_project.hooks.presets"
```

For local, non-distributed work, place the same files in `~/.fetchez/hooks/` and `~/.fetchez/hooks/presets/` instead. See [Plugins & Extensions](plugins_and_extensions.md) for the full picture.

---

**Next up:** See [Streams & Readers](streams.md) to learn how stream-stage hooks receive and process chunked data.
