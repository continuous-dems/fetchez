# Hook Reference

Fetchez hooks provide reusable processing operations that can inspect, modify, filter, or transform data as it moves through a workflow.

Hooks are registered dynamically through the `HookRegistry`. Built-in hooks, user-defined hooks, and hooks supplied by installed extensions can all participate in Fetchez pipelines.

For an introduction to hook stages, presets, and usage, see [Hooks and Presets](../hooks_and_presets.md).

## Documented Hooks

```{toctree}
:maxdepth: 2

remote_archive_footprint
remote_raster_footprint
set_entry
```

## Discovering available hooks
Not every hook has a dedicated documentation page. Fetchez provides additional information through its registry and CLI:

```bash
fetchez hooks list
fetchez hooks info stream-init
```

You can also inspect registered hooks through the Python API:

```python
from fetchez.api import list_hooks, search_hooks

hooks = list_hooks()
matching = search_hooks("raster")
```

See [Hooks and Presets](../hooks_and_presets.md) for information about hook stages, configuration, and extension development.
