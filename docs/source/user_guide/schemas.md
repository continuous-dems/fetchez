# 🏛️ Domain Schemas

While standard Recipes are great for chaining commands, sometimes you need to enforce rigorous geospatial standards across an entire project—like exact arc-second resolutions, cell overlaps, and grid-node vs. pixel-node registration.

Fetchez includes a **Schema Engine** that can automatically mutate your YAML recipes to enforce these rules, saving you from doing tedious geospatial math.

## Using a Schema

Add a `domain` block to the top of your YAML recipe:

```yaml
project:
  name: "My_Strict_Project"

domain:
  schema: "cudem" # Loads the rigorous CUDEM ruleset
  region: [-120.0, -119.75, 33.0, 33.25] # Your exact delivery tile
```

*What happens under the hood?*

By specifying schema: "cudem", the engine intercepts your recipe. It automatically calculates that a CUDEM tile requires a 6-cell overlap at 1/9th arc-second resolution. It expands your fetching bounding box, injects the correct EPSG codes into your gridding hooks, and appends a final raster_crop hook to snap the finished DEM perfectly back to your requested tile.

## Extending Schemas (Plugins)
Fetchez is generic. If you are building a custom tool (like a specialized DEM engine), you can register your own schemas in Python:

```python
from fetchez.schema import BaseSchema, SchemaRegistry

class WeatherSchema(BaseSchema):
    name = "wrf_weather"

    @classmethod
    def apply(cls, config):
        config["region"] = [-180, 180, -90, 90] # Force global fetch
        return config

SchemaRegistry.register(WeatherSchema)
```
