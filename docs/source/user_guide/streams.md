# 🗃️ Streams

The Fetchez Streams API provides a high-performance, memory-safe interface for processing massive datasets (like LiDAR and satellite imagery) in chunks. Rather than loading entire files into RAM, Streams utilize background threading and queues to pipe data continuously from disk to your processing hooks.

## The Python API (`fetchez.read`)

While Fetchez is commonly used via YAML recipes, developers can access the low-level streaming engine directly in Python using `fetchez.read()`.

```python
import fetchez

# Initialize a stream from a local dataset (or remote URL)
stream = fetchez.read(
    "path/to/lidar_data/", ext=".laz", region=[-124.1, -123.9, 44.58, 44.64]
)

# Chain processing hooks
stream.pipe("points2pixels", x_inc="1s", y_inc="1s", want_sums=True).pipe(
    "multi_stack", output="final_dem.tif", overwrite=True
)

# Iterate the stream (This triggers the background engine)
for chunk in stream:
    pass  # Data is processed automatically by the hooks!
```

## Format Readers

At the core of the streaming engine are Readers. Readers are responsible for parsing physical files (CSV, HDF5, LAZ) and yielding chunks of data.

All readers inherit from fetchez.streams.readers.BaseReader. The base class provides automatic spatial indexing: if a dataset is missing an .inf bounding-box sidecar, the BaseReader will automatically scan the file, calculate its bounds, and write the JSON sidecar to dramatically speed up future spatial queries.

Building a Custom Reader
To build a custom reader, extend BaseReader and implement _read_chunks() and _extract_bounds():

```python
import numpy as np
from fetchez.streams.readers.base import BaseReader


class MyCustomReader(BaseReader):
    name = "custom-reader"
    meta_extensions = ["dat", "xyz"]

    def _read_chunks(self):
        """Yields chunks of data from the file."""
        # Open file, read data, and yield (e.g., NumPy structured arrays)
        yield my_data_chunk

    def _extract_bounds(self, chunk):
        """Required for automatic .inf generation."""
        xmin, xmax = np.min(chunk["x"]), np.max(chunk["x"])
        ymin, ymax = np.min(chunk["y"]), np.max(chunk["y"])
        zmin, zmax = np.min(chunk["z"]), np.max(chunk["z"])
        return xmin, xmax, ymin, ymax, zmin, zmax, len(chunk)
```

### Extending Streams (Plugins and Extensions)
Fetchez is generic. If you are building a custom tool and want to create your own format readers or profiles, you can register them either in your project or in the `~/.fetchez` configuration directory and they will be discoverable with the `fetchez.registry.ReaderRegistry` and `fetchez.registry.ProfileRegistry`.
xs
In your project, make a directory called 'streams/readers' and/or 'streams/profiles'; add any python readers and YAML profiles to the appropriate directory and register them with Fetchez in your `pyproject.toml`:

**Streams**

```toml
[project.entry-points."fetchez.streams"]
my_project_readers = "my_project.streams"
```

**Readers**

```toml
[project.entry-points."fetchez.streams.readers"]
my_project_readers = "my_project.streams.readers"
```

**Profiles**

```toml
[project.entry-points."fetchez.streams.profiles"]
my_project_presetes = "my_project.streams.profiles"
```
