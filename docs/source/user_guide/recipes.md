# 🗺️ Recipes

Instead of running long, complex CLI commands every time you want to build a DEM, Fetchez allows you to define your entire workflow in a YAML file called a **Recipe**.

By treating your data pipelines as "Infrastructure as Code," you ensure your data is perfectly reproducible, auditable, and easy to share with your team.

## 🚀 How to Launch a Recipe
Recipes are written in standard YAML. To execute a recipe and build the DEM, simply pass the YAML file to the `fetchez` CLI:

```bash
fetchez recipes/socal_template.yaml
```

Alternatively, you can load and launch recipes directly within a Python driver script using the `fetchez.pipeline` API:

```python
from fetchez.recipe import Recipe

# Load the engine with your recipe and launch
Recipe.from_file("recipes/socal_template.yaml").run()
```

## 📖 Anatomy of a Recipe
A `fetchez` YAML configuration is broken down into specific operational blocks. Here is the generalized structure:

* **1. Project & Execution Metadata**
Defines what you are building and how much compute power to use.

```yaml
project:
  name: "Project_Name"
  description: "Description of the DEM."

execution:
  threads: 4 # Number of parallel download/processing streams

region: [-120.0, -119.0, 33.0, 34.0] # The bounding box: [West, East, South, North]
```

* **2. Modules (The Data Sources)**
The `modules` block lists the data sources `fetchez` will query and ingest. Modules are evaluated in order.

Crucially, you are not limited to remote APIs! You can seamlessly inject your own local or proprietary data into the pipeline using the `local_fs` module.

```yaml
modules:
  # Remote module with arguments
  - module: nos_hydro
    args:
      datatype: "xyz" # Only get the legacy NOS Hydro surveys
      where: "date >= 2000" # Arguments specific to the NOS module
    hooks:
      # These hooks ONLY apply to NOS Hydro data
      - name: stream_data

  # Single Files
  - module: local_fs
    args:
      path: "../local_surveys/new_dredge_project.xyz"
      data_type: "xyz"
    hooks:
      - name: stream_data

  # Directory scan
  - module: local_fs
    args:
      path: "../local_surveys/my_cleaned_multibeam/"
      ext: ".xyz"
      data_type: "multibeam"
      gen_inf: True
    hooks:
      - name: stream_data

  # Simple remote module
  - module: tnm
    args:
      formats: "GeoTIFF"
    # Notice this module has no specific hooks; it will just download the files.
```

* **3. Global Hooks (The Assembly Line)**
The `global_hooks` block defines the processing pipeline. While module hooks only touch specific data, **Global Hooks process the combined pool of data from all modules.**

```yaml
global_hooks:
  - name: set_weight
    args:
      rules:
        nos_hydro: 10.0
        tnm: 2.0

  - name: multi_stack
    args:
      res: "1s"
      output: "final_stack.tif"
```

## 🪝 Understanding Hooks and the Lifecycle
Hooks are the specialized tools that process data. It is critical to understand when they run. `fetchez` processes hooks in three distinct stages:

* **1. PRE Stage:** Runs before downloads begin.

*Use case*: Filtering the list of URLs, assigning stack weights (set_weight), or generating boundary masks (osm_landmask) before processing starts.

* **2. FILE Stage:** Runs during the download loop on each individual file.

*Use case*: Unzipping archives, converting formats, or streaming point clouds directly into a grid accumulator (multi_stack).

* **3. POST Stage:** Runs after all files have been downloaded and streamed.

*Use case*: Spatial interpolation (sm_cudem), blending seams (sm_blend), and final output cropping.

**Global vs. Module Hooks**
* **Module Hooks (modules.hooks):** Only execute on the files fetched by that specific module.

* **Global Hooks (global_hooks):** Execute on the entire, aggregated dataset from all modules simultaneously.

## 💡 Pro-Tips for Recipe Writers
* **1. Keep it DRY with YAML Anchors**
If multiple modules require the exact same set of hooks (e.g., streaming and cropping), do not copy and paste. Define an anchor (&) and alias it (*):

```yaml
_definitions:
  standard_stream: &standard_stream
    - name: stream_data
    - name: spatial_crop
      args: { buffer: 0.05 }

modules:
  - module: dav
    hooks: *standard_stream
  - module: csb
    hooks: *standard_stream
```

* **2. Path Resolution is Automatic**
When you define a file output in a hook (e.g., output: "stack.tif"), `fetchez` automatically saves it relative to where the YAML file is located. You do not need to hardcode absolute paths!

* **3. Inspect Available Tools**
Not sure what a hook does or what arguments it takes? Ask the CLI:

* List all hooks: `fetchez --list-hooks`

* Get specific hook documentation: `fetchez --hook-info sm_cudem`