# 🗺️ Recipes

Recipes define reusable geospatial data workflows using YAML configurations or Python objects. They describe the data sources, processing hooks, execution settings, and validation rules needed to build a dataset.

A recipe can be executed directly from the CLI, run programmatically across one or more geographic regions, or compiled into a prepared pipeline for integration with other applications.

> **Running example:** Throughout the [Usage](usage.md), [Modules](modules_and_bundles.md), and [Hooks](hooks_and_presets.md) pages, we've been building a pipeline to fetch Copernicus DEM tiles around San Diego. This page shows you how to save that pipeline as a recipe, then extend it with modifiers, schemas, and programmatic control.

## How to Execute a Recipe

Recipes are written in standard YAML. To execute a recipe and start fetching data, pass the YAML file to the `fetchez` CLI:

```bash
fetchez run recipes/san_diego_dem.yaml
```

Alternatively, load and launch recipes directly within a Python driver script:

```python
from fetchez.recipe import Recipe

# Load the engine with your recipe and launch
for result in Recipe.from_file("recipes/san_diego_dem.yaml").run():
    print(result[2])  # completed batch name
```

Or use the shortcut:

```python
import fetchez

fetchez.run_recipe("san_diego_dem.yaml")
```

## Anatomy of a Recipe

A Fetchez YAML configuration is organized into specific operational blocks. Here is the general structure for a project that downloads Topography and Boundary data, unzips it, and audits the result:

### 1. Project & Execution Metadata

Defines what you are building and how much compute capacity to allocate.

```yaml
project:
  name: "San_Diego_Coastal_Data"
  description: "Pulling COP-30 DEM tiles for local analysis."

execution:
  threads: 4  # Number of parallel download streams

region: [-117.3, -116.8, 32.6, 33.0]  # West, East, South, North
region_srs: EPSG:4326  # The CRS of the bounding box
```

Note that `region` and `modules` are **top-level** fields, not nested under `project`.

### 2. Modules (The Data Sources)

The `modules` block lists the data sources Fetchez will query and ingest. Modules are evaluated in order.

```yaml
modules:
  # Download NOAA Nautical Charts
  - module: charts
    hooks:
      # These hooks ONLY apply to charts data
      - name: unzip
        args:
          remove: true  # Delete the .zip after extracting

  # Download Copernicus Topography
  - module: copernicus
    args:
      datatype: "1"  # COP-30
    hooks:
      - name: checksum
        args:
          algo: "sha256"

  # Seamlessly include local data in the pipeline!
  - module: local_fs
    args:
      path: "../local_surveys/field_notes/"
      ext: ".csv"
```

Each module's `hooks` list applies only to that module's data — the same scoping rule described in [Usage](usage.md).

### 3. Global Hooks (The Assembly Line)

The `global_hooks` block defines the processing pipeline applied to the combined pool of data from all modules.

```yaml
global_hooks:
  # Runs after ALL downloads and unzipping are finished
  - name: audit
    args:
      file: "san_diego_data_audit.json"
```

#### Understanding Hooks and the Lifecycle

See [Hooks & Presets](hooks_and_presets.md) for a complete treatment of the four stages (manifest, file, stream, collection) and how they apply to recipes.

#### Global vs. Module Hooks

* **Module Hooks** (`modules[].hooks`) — Execute only on files fetched by that specific module
* **Global Hooks** (`global_hooks`) — Execute on the entire, aggregated dataset from all modules

## Advanced Execution: Placeholders, Modifiers, and Schemas

Fetchez provides advanced tools to alter and validate your recipes at runtime without modifying the underlying YAML files.

### Runtime Context Placeholders

Fetchez expands explicitly requested runtime variables in recipe string values using `%placeholder%` syntax. This also works in Python-created recipes when passing constructor arguments. Existing Python component instances are not modified or interpolated.

**Important YAML Formatting Note:** Enclose any string containing a placeholder in quotes (e.g., `"%shared_cache%"`).

| Placeholder | Resolution |
|-------------|------------|
| `%name%` | The project name defined in the recipe |
| `%batch_name%` | The name of the current batch/tile being processed (or the formatted bounding box) |
| `%shared_cache%` | Absolute path to the shared cache directory (falls back to the batch's tile directory if no cache is specified) |
| `%outdir%` | Base output directory for the execution |
| `%tile_dir%` | Specific working directory for the current batch iteration |
| `%region_srs%` | The spatial reference system (CRS) of the target region |
| `%cache_dir%` | Resolves in the same way as `%shared_cache%` |

**Example Usage:**

```yaml
modules:
  - module: tnm
    args:
      outdir: "%tile_dir%"
    hooks:
      - name: stream_reproject
        args:
          cache_dir: "%shared_cache%"
global_hooks:
  - name: multi_stack
    args:
      output: "%name%_%batch_name%_stack.tif"
```

### Modifiers

The Modifier Engine intercepts recipes as they are loaded and mutates them before core execution. This allows for complete runtime control of the pipeline without editing the YAML file.

#### Using a Modifier

Add a `modifiers` argument to the top of your YAML recipe:

```yaml
---
project:
  name: "My_Project"

modifiers:
  - name: exclude_module
    args:
      modules: margrav/charts

region: [-120.0, -119.75, 33.0, 33.25]

modules:
  - bundle: my-bathymetry-bundle
```

**What happens:** The `exclude_module` modifier removes the named `margrav` and `charts` modules from the bundle before the recipe runs.

**Use the modifier in the CLI:**

```bash
fetchez run my_project.yaml --modifier exclude_module:modules=margrav/charts
```

### Schemas

The Schema Engine scans recipes to enforce rules or validate structure and purpose.

#### Using a Schema

Add a `schemas` argument to the top of your YAML recipe:

```yaml
project:
  name: "My_Strict_Project"

schemas:
  - name: "quarter-degree-tile"

region: [-120.0, -119.75, 33.0, 33.25]  # Your exact delivery tile
```

**What happens:** The `quarter-degree-tile` schema checks that the region snaps to a quarter-degree tile in WGS84, returning validity along with any errors found.

**Use the schema in the CLI:**

```bash
fetchez run -R -120/-119.75/33/33.25 --schema quarter-degree-tile my_strict_project.yaml
```

## High-Level Execution: `Recipe.run()`

This is the recommended interface for ordinary YAML workflows and multi-region batch processing:

```python
from fetchez.recipe import Recipe

recipe = Recipe.from_file("my_recipe.yaml")

for config, region, name, cache, outdir, tile_dir in recipe.run(
    outdir="outputs",
    shared_cache="cache",
):
    print(f"Completed {name}: {tile_dir}")
```

## Low-Level Preparation: `Recipe.compile()`

This prepares a single pipeline without executing it:

```python
from fetchez.recipe import Recipe, RecipeContext
from fetchez.spatial import Region

recipe = Recipe.from_dict({
    "project": {"name": "custom_pipeline"},
    "modules": [
        {"module": "tnm"},
    ],
    "global_hooks": [
        {"name": "audit"},
    ],
})

context = RecipeContext(
    region=Region.from_list([-120, -119.75, 33, 33.25]),
    name="custom_pipeline",
)

plan = recipe.compile(context)

# Inspect the prepared components
print(plan.modules)
print(plan.global_hooks)

# Execute when ready
plan.execute()
```

## Python Runtime Components (Without Registration)

Recipes can be constructed in Python using custom `FetchModule` and `FetchHook` subclasses **without registering them**. A Python recipe may mix registered component names, Python class references, and already-initialized component instances in its `modules`, `global_hooks`, and module-local `hooks` lists.

During compilation, registered component names and Python classes are resolved into new component instances. Each compilation creates fresh objects for class-based definitions, allowing the same Recipe to be compiled independently for different regions or execution contexts. Preinitialized component instances are preserved by identity and retain their original configuration.

### Pass Classes with Constructor Arguments

Use a class reference when you want Recipe to create a **fresh component for each batch**. Arguments may use the same `%placeholder%` syntax as YAML recipes:

```python
from fetchez.recipe import Recipe
from my_project.modules import MyModule
from my_project.hooks import MyOutputHook

recipe = Recipe.from_dict({
    "project": {"name": "survey"},
    "region": [-120, -119.75, 33, 33.25],
    "modules": [
        {"module": MyModule, "args": {"dataset": "bathymetry"}},
    ],
    "global_hooks": [
        {"name": "audit"},  # registered name
        {"name": MyOutputHook, "args": {
            "output": "%name%_%batch_name%.tif",
        }},
    ],
})

# run() is an iterator; iterate to execute the workflow
for batch in recipe.run(outdir="outputs"):
    print("Completed:", batch[2])
```

A class is resolved directly; no entry point, user plugin folder, or registry registration is required. Recipe provides the normal batch region and module-hook context when creating module classes, and interpolates requested placeholders before calling constructors. **Do not put `%placeholder%` strings into an existing instance expecting Recipe to reconfigure it afterward.**

### Pass Existing Instances Unchanged

Preinitialized components can also participate in a recipe. Recipe preserves their **object identity and configured state** (including existing hooks, regions, queues, or connections) rather than cloning, resetting, or modifying them:

```python
from queue import Queue
from fetchez.recipe import Recipe
from my_project.hooks import MyQueueHook
from my_project.modules import MyModule

queue = Queue()
source = MyModule(dataset="bathymetry")
sink = MyQueueHook(queue=queue)

recipe = Recipe.from_dict({
    "modules": [source],
    "global_hooks": [sink],
})

# The same source and sink objects are used by Recipe
for batch in recipe.run():
    pass
```

**Batching and state:** Class references are instantiated anew for each batch; instances are reused **as-is** across batches. Recipe does not automatically change an instance's `src_region`, output directory, constructor arguments, or internal caches. For a region-dependent module, prefer `{"module": MyModule, "args": {...}}` over a preinitialized instance so each batch receives its own region. Shared, stateful hook instances can be useful (for example, a queue sink), but the caller is responsible for their lifecycle and for draining bounded queues while the producer runs.

Instances should be supplied directly, not with extra `args` or `hooks` intended to reconfigure them. Registered names and YAML recipes retain their existing behavior. Only Python-created recipes can contain live class references or objects; YAML should continue to use registered component names. Recipes containing runtime objects cannot be exported as equivalent CLI commands or serialized to JSON without replacing those references with registered names.

## Extending Recipes (Plugins and Extensions)

If you are building a custom tool (like a specialized DEM engine), you can register your own recipes, modifiers, and schemas either in your project or in the `~/.fetchez` configuration directory. They will be discoverable with `fetchez.registry`.

In your project, create a directory called `recipes`; add any YAML recipes there, and any Python source files in `recipes/modifiers` or `recipes/schemas`. Register them in `pyproject.toml`:

**Recipes**

```toml
[project.entry-points."fetchez.recipes"]
my_project_recipes = "my_project.recipes"
```

**Modifiers**

```toml
[project.entry-points."fetchez.recipes.modifiers"]
my_project_modifiers = "my_project.recipes.modifiers"
```

**Schemas**

```toml
[project.entry-points."fetchez.recipes.schemas"]
my_project_schemas = "my_project.recipes.schemas"
```

---

**Next up:** See [Plugins & Extensions](plugins_and_extensions.md) to learn how to register local plugins or create distributable extensions with custom modules, hooks, and recipes.
