# Readers Reference

Fetchez provides a composable streaming interface for acquiring files, decoding them with registered readers, and processing data in chunks.

For an introduction to stream, readers and profiles, see [Streams and Readers](../streams.md).

## Documented Readers

```{toctree}
:maxdepth: 2

raster_streams
```

## Discovering available readers
Not every reader, profile or datatype has a dedicated documentation page. Fetchez provides additional information through its registry and CLI:

```bash
fetchez streams readers list
fetchez streams readers info rasterio
```

You can also inspect registered hooks through the Python API:

```python
from fetchez.api import list_readers, search_readers

readers = list_readers()
matching = search_readers("raster")
```
