# 🗺️ Recipes

Instead of running long, complex CLI commands every time you want to build a dataset, `fetchez` allows you to define your entire workflow in a YAML file called a **Recipe**.

By treating your data pipelines as *Infrastructure as Code*, you ensure your data pulls are perfectly reproducible, auditable, sharable..

## 🚀 How to Launch a Recipe
Recipes are written in standard YAML. To execute a recipe and start fetching data, simply pass the YAML file to the `fetchez` CLI:

```bash
fetchez recipes/my_archive_project.yaml
Alternatively, you can load and launch recipes directly within a Python driver script using the `fetchez.recipe` API:

```python
from fetchez.recipe import Recipe

# Load the engine with your recipe and launch
Recipe.from_file("recipes/my_archive_project.yaml").cook()
```

## 📖 Anatomy of a Recipe
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

## 🪝 Understanding Hooks and the Lifecycle
Hooks are the specialized tools that intercept and process your data. It is critical to understand when they run. `fetchez` processes hooks in three distinct stages:

### PRE Stage: Runs before downloads begin.

*Use case:* Filtering the list of URLs based on regex, limiting the maximum number of files to download, or authenticating tokens.

### FILE Stage: Runs during the download loop on each individual file.

*Use case:* Unzipping archives immediately as they arrive, verifying checksums, or piping the file path to standard output.

### POST Stage: Runs after all files have been downloaded and processed.

*Use case:* Generating a JSON audit log, zipping the final output directory into a clean tarball, or sending a Slack notification that the job is done.

### Global vs. Module Hooks

* **Module Hooks** (`modules.hooks`): Only execute on the files fetched by that specific module. For example, you might only want to run the unzip hook on USGS data, but leave Copernicus files as tarballs.

* **Global Hooks** (`global_hooks`): Execute on the entire, aggregated dataset from all modules simultaneously.
