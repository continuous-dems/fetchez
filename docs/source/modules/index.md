# Module Catalog

Modules are registered dynamically through the `ModuleRegistry`. Built-in modules, user-defined modules, and modules supplied by installed extensions can all participate in Fetchez pipelines.

For an introduction to modules, see [Modules and Bundles](/user_guide/modules_and_bundles.md).

```{module-table}
```

```{toctree}
:maxdepth: 1

http_index
rest_api
stac
thredds
tnm
earthaccess
```

## Discovering available modules
Not every module has a dedicated documentation page. Fetchez provides additional information through its registry and CLI:

```bash
fetchez modules list
fetchez modules info copernicus
```

You can also inspect registered modules through the Python API:

```python
from fetchez.api import list_modules, search_modules

modules = list_modules()
matching = search_modules("bathymetry")
```

> See [Modules and Bundles](/user_guide/modules_and_bundles.md) for information about modules, configuration, and extension development.
