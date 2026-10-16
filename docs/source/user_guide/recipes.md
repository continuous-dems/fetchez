# 🗺️ Recipes

Fetchez Recipes define reusable geospatial data workflows using YAML configurations or Python objects. Recipes describe the data sources, processing hooks, execution settings, and validation rules needed to build a dataset.

A Recipe can be executed directly from the CLI, run programmatically across one or more geographic regions, or compiled into a prepared pipeline for integration with other Python applications.

This separation between workflow definition, preparation, and execution makes Recipes useful both for reproducible standalone data processing and as building blocks for larger geospatial ETL systems.

## How to Launch a Recipe
Recipes are written in standard YAML. To execute a recipe and start fetching data, simply pass the YAML file to the `fetchez` CLI:

```bash
fetchez recipes run recipes/my_archive_project.yaml
```

Alternatively, you can load and launch recipes directly within a Python driver script using the `fetchez.recipe` API:

```python
from fetchez.recipe import Recipe

# Load the engine with your recipe and launch
for result in Recipe.from_file("recipes/my_archive_project.yaml").run():
    print(result[2])  # completed batch name
```

```python
# run a recipe from the fetchez api
import fetchez

fetchez.run_recipe("my_recipe.yaml")
```


## Anatomy of a Recipe
A `fetchez` YAML configuration is broken down into specific operational blocks. Here is a generalized structure for a project that downloads Topography and Boundary data, unzips it, and audits the result:

### 1. **Project & Execution Metadata**
Defines what you are building and how much compute power to use.

```yaml
project:
  name: "Miami_Coastal_Data"
  description: "Pulling raw shapefiles and TIFFs for local analysis."

execution:
  threads: 4 # Number of parallel download streams

region: [-80.5, -80.0, 25.5, 26.0] # The bounding box: [West, East, South, North]
region_srs: EPSG:4326 # The srs of the bounding box
```

### 2. **Modules** (The Data Sources)
The `modules` block lists the data sources `fetchez` will query and ingest. Modules are evaluated in order.

```yaml
modules:
  # Download NOAA Nautical Charts
  - module: charts
    hooks:
      # These hooks ONLY apply to charts data
      - name: unzip
        args:
          remove: true # Delete the .zip after extracting

  # Download Copernicus Topography
  - module: copernicus
    args:
      datatype: "1" # COP-30
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

### 3. **Global Hooks** (The Assembly Line)
The `global_hooks` block defines the processing pipeline. While module hooks only touch specific data, Global Hooks process the combined pool of data from all modules.

```yaml
global_hooks:
  # Runs after ALL downloads and unzipping are finished
  - name: audit
    args:
      file: "miami_data_audit.json"
```

#### Understanding Hooks and the Lifecycle
Hooks are the specialized tools that intercept and process your data. It is critical to understand when they run. `fetchez` processes hooks in four distinct stages:

* **PRE/MANIFEST Stage:** Runs before downloads begin.
  *Use case:* Filtering the list of URLs based on regex, limiting the maximum number of files to download, or authenticating tokens.

* **FILE Stage:** Runs during the download loop on each individual file.
  *Use case:* Unzipping archives immediately as they arrive, verifying checksums, or piping the file path to standard output.

* **STREAM Stage:** Runs after the FILE Stage having invoked the `stream-init` hook.

* **POST/COLLECTION Stage:** Runs after all files have been downloaded and processed.
  *Use case:* Generating a JSON audit log, zipping the final output directory into a clean tarball, or sending a Slack notification that the job is done.

#### Global vs. Module Hooks

* **Module Hooks** (`modules.hooks`): Only execute on the files fetched by that specific module. For example, you might only want to run the unzip hook on USGS data, but leave Copernicus files as tarballs.

* **Global Hooks** (`global_hooks`): Execute on the entire, aggregated dataset from all modules simultaneously.

## Advanced Execution: Placeholders, Modifiers and Schemas

Fetchez provides advanced tools to alter and validate your recipes at runtime without modifying the underlying YAML files.

### Runtime Context Placeholders
Fetchez expands explicitly requested runtime variables in recipe string values using `%placeholder%` syntax. This also works in Python-created recipes when passing a class and constructor arguments. Existing Python component instances are not modified or interpolated.

**Important YAML Formatting Note:** To ensure your YAML parses correctly, you must enclose any string containing a placeholder in quotes (e.g., `"%shared_cache%"`).

Available placeholders include:
* **`%name%`**: The project name defined in the recipe.
* **`%batch_name%`**: The name of the current batch/tile being processed (or the formatted bounding box).
* **`%shared_cache%`**: The absolute path to the shared cache directory (falls back to the batch's tile directory if no cache is specified).
* **`%outdir%`**: The base output directory for the execution.
* **`%tile_dir%`**: The specific working directory for the current batch iteration.
* **`%region_srs%`**: The spatial reference system (CRS) of the target region.
* **`%cache_dir%`**: Resolves in the same way as `%shared_cache%`.

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
Fetchez includes a **Modifier Engine** in its `ModifierRegistry` that can automatically mutate your YAML recipes as they are loaded, allowing for complete runtime control of the pipeline.

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

*What happens under the hood?*

By specifying the modifier: `exclude_module`, the engine intercepts your recipe and removes the named `margrav` and `charts` modules from the module Bundle `my-bathymetry-bundle`. Modifiers take an input recipe config and do something to or with it and return the possibly mutated bundle, right before sending to the core Fetchez engine for processing.


**Use the modifier in the cli**

```bash
fetchez recipes run my_project.yaml --modifier exclude_module:modules=margrav/charts
```

### Schemas
Fetchez includes a **Schema Engine** in its `SchemaRegistry` that automatically scans your YAML recipes to enforce rules or otherwise validate the recipe structure or purpose.

#### Using a Schema

Add a `schemas` argument to the top of your YAML recipe, in this example we'll use a theoretical `schema` that would make sure the `region` parameter is a strict 1/4 degree tile:

```yaml
project:
  name: "My_Strict_Project"

schemas:
  - name: "quarter-degree-tile"
region: [-120.0, -119.75, 33.0, 33.25] # Your exact delivery tile
```

*What happens under the hood?*

By specifying schema: `quarter-degree-tile`, the engine intercepts your recipe and checks your region to make sure it snaps directly to a quarter degree tile in WGS84. It will return the validity of the recipe based on that schema along with any errors it found.

**Use the schema in the CLI**

```bash
fetchez recipes run -R -120/-119.75/33/33.25 --schema quarter-degree-tile my_strict_project.yaml
```

## High-level execution: `Recipe.run()`

This is the recommended interface for ordinary YAML workflows and multi-region batch processing.

```python
from fetchez.recipe import Recipe

recipe = Recipe.from_file("my_recipe.yaml")

for config, region, name, cache, outdir, tile_dir in recipe.run(
    outdir="outputs",
    shared_cache="cache",
):
    print(f"Completed {name}: {tile_dir}")
```

## Low-level preparation: `Recipe.compile()`

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

# Inspect the prepared components.
print(plan.modules)
print(plan.global_hooks)

# Execute when ready.
plan.execute()
```

## Python Runtime Components (Without Registration)

Recipes can also be constructed in Python using custom `FetchModule` and `FetchHook` subclasses **without registering them**. A Python recipe may mix registered component names, Python class references, and already-initialized component instances in its `modules`, `global_hooks`, and module-local `hooks` lists.

During compilation, registered component names and Python classes are resolved into new component instances. Each compilation creates fresh objects for class-based definitions, allowing the same Recipe to be compiled independently for different regions or execution contexts. Preinitialized component instances are preserved by identity and retain their original configuration.

### Pass classes with constructor arguments

Use a class reference in a recipe definition when you want Recipe to create a **fresh component for each batch**. Arguments may use the same explicit `%placeholder%` syntax as YAML recipes:

```python
from fetchez.recipe import Recipe
from my_project.modules import MyModule       # FetchModule subclass
from my_project.hooks import MyOutputHook       # FetchHook subclass

recipe = Recipe.from_dict({
    "project": {"name": "survey"},
    "region": [-120, -119.75, 33, 33.25],
    "modules": [
        {"module": MyModule, "args": {"dataset": "bathymetry"}},
    ],
    "global_hooks": [
        {"name": "audit"},                # registered name
        {"name": MyOutputHook, "args": {
            "output": "%name%_%batch_name%.tif",
        }},
    ],
})

# run() is an iterator; iterate it to execute the workflow.
for batch in recipe.run(outdir="outputs"):
    print("Completed:", batch[2])
```

A class is resolved directly; no entry point, user plugin folder, or registry registration is required. Recipe still provides the normal batch region and module-hook context when creating **module classes**, and interpolates requested placeholders before calling constructors. Do not put `%placeholder%` strings into an existing instance expecting Recipe to reconfigure it afterward.

### Pass existing instances unchanged

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

# The same source and sink objects are used by Recipe.
for batch in recipe.run():
    pass
```

**Batching and state:** class references are instantiated anew for each batch; instances are reused **as-is** across batches. Recipe does not automatically change an instance's `src_region`, output directory, constructor arguments, or internal caches. For a region-dependent module, prefer `{"module": MyModule, "args": {...}}` over a preinitialized instance so each batch receives its own region. Shared, stateful hook instances can be useful (for example, a queue sink), but the caller is responsible for their lifecycle and for draining bounded queues while the producer runs.

Instances should be supplied directly, not with extra `args` or `hooks` intended to reconfigure them. Registered names and YAML recipes retain their existing behavior. Only Python-created recipes can contain live class references or objects; YAML should continue to use registered component names. Recipes containing runtime objects cannot be exported as equivalent CLI commands or serialized to JSON without replacing those references with registered names.

## Extending Recipes (Plugins and Extensions)
Fetchez is generic. If you are building a custom tool (like a specialized DEM engine), you can register your own recipes, modifiers and schemas either in your project or in the `~/.fetchez` configuration directory and they will be discoverable with the `fetchez.registry`

In your project, make a directory called 'recipes'; add any YAML recipes to that directory, add any python source files in 'recipes/modifiers' or 'recipe/schemas' and register them with `fetchez` in your `pyproject.toml`:

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
