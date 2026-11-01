# 🛠️ Usage

The `fetchez` command line tool lets you chain data sources (Modules and Bundles) with processing steps (Hooks and Presets) into cohesive pipelines.

This guide shows you how to build and execute workflows, from simple one-liners to exported recipes you can share and replay.

## Your First Pipeline

Let's fetch elevation data for San Diego from a STAC catalog as a quick introduction:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  list_only \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 5
```

**What this does:**

* `-R 'loc:san diego, ca'` — Sets the region of interest (San Diego area)
* `list_only` — A Hook that inspects matching entries without downloading them
* `stac` — A Module that queries a STAC catalog
* `--url`, `--collections`, `--assets` — Arguments to the `stac` module
* `--limit 5` — Returns only 5 matching results for this exploration

Run this command to see what data is available before committing to a full download.

## Pipeline Composition Rules

Fetchez builds workflows by chaining components from left to right. Understanding **scope** is critical:

| Component Position                        | Applies To                                         |
|-------------------------------------------|----------------------------------------------------|
| Hooks/Presets **before** the first source | The entire pipeline (global)                       |
| Hooks/Presets **after** a Module/Bundle   | That specific source only                          |
| New Module/Bundle encountered             | Starts a new scope; previous hooks no longer apply |

### Visual Examples

**Global hook before source:**
```bash
fetchez build audit tnm
```
- `audit` → applies to all modules below it (none yet)
- `tnm` → the data source

**Hook attached to a single source:**
```bash
fetchez build \
	tnm \
	exec \
	--cmd "gdalwarp -tr 0.0002777777777777778 0.0002777777777777778 {file} {output}" \
	--suffix "_warp1s"
```
- `tnm` → the data source
- `exec` → applies only to `tnm` data
- `--cmd` → argument to `exec`
- `--suffix` → argument to `exec`

**Multiple independently processed sources:**
```bash
fetchez build \
	audit \
	tnm \
	exec \
	--cmd "gdalwarp -tr 0.0002777777777777778 0.0002777777777777778 {file} {output}" \
	--suffix "_warp1s" \
	copernicus \
	checksum
```
- `audit` → global hook (applies to everything)
- `tnm` → first source
- `exec` → applies only to `tnm` data
- `copernicus` → second source
- `checksum` → applies only to `copernicus` data

Once you encounter a new Module or Bundle, the previous hooks stop applying.

## Downloading Data

To actually download data, remove `list_only`:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 10
```

Fetchez will:
1. Query the STAC catalog
2. Download matching assets to a cache
3. Apply any hooks attached after `stac`

## Adding Processing Hooks

Hooks let you transform, filter, or observe data as it flows through the pipeline. Here's how to unzip archives and generate an audit log:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  audit \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 10 \
  exec \
  --cmd "gdal_translate {file} {output} -co COMPRESS=DEFLATE" \
  --suffix "_compressed \
  --update_entry True"
```

**Breakdown:**
- `audit` (global) → logs everything that happens
- `stac` → fetches the DEM tiles
- `exec` → runs `gdal_translate` on each file to create compressed versions

> **Note:** GDAL must be installed separately for the `exec` hook to work. See [Installation](installation.md) for dependencies.

## Saving and Replaying Workflows

You don't want to type this command every time. Export it as a reusable recipe:

```bash
fetchez build \
  -R 'loc:san diego, ca' \
  --export san_diego_dem.yaml \
  audit \
  stac \
  --url https://earth-search.aws.element84.com/v1 \
  --collections cop-dem-glo-30 \
  --assets data \
  --limit 10 \
  exec \
  --cmd "gdal_translate {file} {output} -co COMPRESS=DEFLATE" \
  --suffix "_compressed \
  --update_entry True"
```

This writes `san_diego_dem.yaml` to your current directory. Run it later with:

```bash
fetchez run san_diego_dem.yaml
```

> **Caution:** The exported recipe retains `list_only` if it was in your command. Remove that step before running to actually fetch data.

## Discovering Available Components

Before building pipelines, explore what's installed:

```bash
# List all data source modules
fetchez modules list

# List curated groups of modules
fetchez modules bundles list

# List all processing hooks
fetchez hooks list

# List hook presets (macro combinations)
fetchez hooks presets list
```

Inspect a specific component's options:

```bash
fetchez build stac --help
fetchez build unzip --help
```

## Component Argument Syntax

Arguments follow the component they configure:

```bash
fetchez build \
  stac \
  --url https://example.com \
  --collections my-collection \
  checksum \
  --algo sha256
```

Short flags (`-R`) are available for common options like region. Long flags (`--region`) work too.

## Quick Reference

| Goal | Command Pattern |
|------|-----------------|
| Explore data without downloading | Add `list_only` before the source |
| Download and process | Remove `list_only`, add hooks after source |
| Log everything | Add `audit` as a global hook |
| Transform files | Use `exec` with `{file}` and `{output}` placeholders |
| Save for later | Add `--export recipe.yaml` |
| Replay saved workflow | `fetchez run recipe.yaml` |

## Using the Python API

The same workflows can be built in Python:

```python
import fetchez

# Fetch with hooks applied
files = fetchez.get(
    "stac",
    url="https://earth-search.aws.element84.com/v1",
    collections=["cop-dem-glo-30"],
    assets=["data"],
    region=[-118.0, -116.0, 32.5, 33.5],
    hooks=["unzip", "audit"],
)
```

For complex workflows, recipes (YAML) remain the preferred approach for reproducibility. See [Recipes](recipes.md).

---

## What's Next?

Now that you've built your first pipeline, learn about the building blocks:

* **[Modules & Bundles](modules_and_bundles.md)** — Deep dive into data sources: how they work, how to configure them, and how to create your own
* **[Hooks & Presets](hooks_and_presets.md)** — Master the processing layer: hooks, stages, presets, and how they compose
* **[Recipes](recipes.md)** — Create advanced workflows with modifiers, schemas, and programmatic recipe construction

Or jump to the full [Command Line Interface](cli_usage.md) reference for complete syntax and all available commands.
