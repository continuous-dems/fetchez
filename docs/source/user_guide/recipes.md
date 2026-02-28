# 📜 Recipes

Instead of running long, complex CLI commands every time you want to build a DEM, Fetchez allows you to define your entire workflow in a YAML file called a **Recipe**.

By treating your data pipelines as "Infrastructure as Code," you ensure your data is perfectly reproducible, auditable, and easy to share with your team.

## Executing a Recipe

To run a recipe, simply pass the YAML file to the `fetchez` CLI:

```bash
fetchez my_project.yaml
```

## Anatomy of a Recipe
A Fetchez YAML configuration is broken down into specific blocks:

```yaml
project:
  name: "SoCal_Tile_01"
  description: "Southern California Coastal DEM"

region: [-120.0, -119.0, 33.0, 34.0] # Bounding box: [West, East, South, North]

modules:
  # The Data Sources (Ingredients)
  - module: nos_hydro
    args:
      where: "date >= 2000"
      weight: 10.0

  - module: tnm
    args:
      formats: "GeoTIFF"
      weight: 5.0

global_hooks:
  # The Assembly Line (Processing)
  - name: stream_data
  - name: multi_stack
    args:
      output: "final_stack.tif"
````

* **modules**: Defines the data sources to query (APIs or local files).

* **global_hooks**: Defines the processing pipeline applied to the combined data.