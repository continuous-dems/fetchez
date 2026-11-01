# 🗃️ Streams & Readers

Fetchez provides a composable streaming interface for acquiring files, decoding them with registered readers, and processing data in chunks. This is a lightweight alternative to full YAML recipes when you're building interactive workflows or integrating Fetchez into another application.

> **Running example:** In [Usage](usage.md) and [Hooks](hooks_and_presets.md), we fetched DEM tiles, unzipped them, and ran `gdal_translate`. Streams are useful when you need to **read the actual data** (e.g., extract elevation values, build a DataFrame, compute statistics) rather than just manage files.

## Quick Start

```python
from fetchez.api import read

stream = read("observations.csv").pipe(
    "stream-init",
    profile="csv-default",  # use a profile registered in your environment
)

for chunk in stream:
    print(chunk)
```

**What's happening:**

* `read()` returns a `BaseStream` — it does not immediately fetch or decode data
* Module objects are constructed when `read()` is called
* Source discovery, fetching, reader initialization, and stream processing occur **during iteration**
* Each new iteration runs the pipeline again; caches may avoid repeating some work

The `BaseStream` runs its processing pipeline in a background thread and uses a bounded queue to deliver chunks to the caller. Streaming reduces memory use compared to loading an entire dataset, although individual readers and hooks may have their own buffering requirements.

For detailed documentation of individual streams, readers, profiles, and data types — including configuration, examples, and limitations — see the [Reader Reference](streams/index.md).

Not every registered reader has a dedicated documentation page. Use the `fetchez streams` CLI commands or the `StreamRegistry`, `ReaderRegistry`, or `ProfileRegistry` to discover additional built-in and extension-provided streams and readers.

```{toctree}
:maxdepth: 2

streams/index
```

## Choosing an API

| API | Use it to | Result |
|-----|-----------|--------|
| `fetchez.get()` | Download data from a particular module | Local file paths |
| `fetchez.read()` | Build and consume a lightweight stream of data | Lazy `BaseStream` |
| `stream.pipe()` | Add a reader initializer or processing hook to a stream | The same stream, for chaining |
| Recipes / `Pipeline` | Orchestrate more involved acquisition and processing workflows | Recipe-driven execution with modifiers, schemas, and multi-region support |

## Defining Sources

`read(sources, region=None, shared_cache=None)` accepts:

* A source string (registered module, bundle, or local file)
* A source-definition dictionary
* A list of either

Strings are convenient for quick experiments; dictionaries give you explicit control over module arguments:

```python
stream = read({
    "module": "tnm",
    "args": {"products": "1m"},
})
```

Sources can be combined, each with independent module arguments:

```python
stream = read([
    {"module": "local_fs", "args": {"path": "observations_a.csv"}},
    {"module": "local_fs", "args": {"path": "observations_b.csv"}},
])
```

`region` specifies the region for discovery and processing where supported by the module. `shared_cache` configures a shared location for eligible downloaded resources.

### Configuration Scope Matters

* `args` inside a source definition belongs to that **module**
* Reader configuration belongs to a **profile** or an explicit `stream-init` hook
* Do not assume arbitrary entry metadata is forwarded as reader arguments

## Readers, Data Types, Profiles, and Streams

These terms describe different parts of the pipeline:

| Concept | Meaning | Example |
|---------|---------|---------|
| `data_type` | Generic representation of an entry | `raster`, `vector`, `archive` |
| `profile` | Selected reader and its default options | A registered CSV profile |
| Reader | Implementation that decodes the source | CSV reader implementation |
| `stream_type` | Representation produced by the reader | `list-stream`, `point-stream`, `raster-stream` |

A data type does not necessarily select a domain-specific interpretation. A raster might contain elevation, imagery, or weather information. An explicit profile lets the caller select the intended reader and configuration.

See [Hooks & Presets](hooks_and_presets.md) for how hooks advertise `accepts` and `produces` stream types.

### Explicit Reader Initialization

Use `.pipe("stream-init", ...)` when you need control over the reader:

```python
stream = read("observations.csv").pipe(
    "stream-init",
    profile="csv-default",
    chunk_size=10000,
)

for chunk in stream:
    process(chunk)
```

The profile supplies reader defaults; explicitly supplied `stream-init` options can override them. The profile name above is illustrative — use `list_profiles()` to discover the profiles installed in your environment, and consult the selected reader for its supported options.

If a pipeline already has an entry profile or a suitable data-type default, it can resolve a reader without an explicit profile override. Fetchez can also insert a default stream initializer when stream-stage hooks are present and no initializer or existing stream is available. **Explicit initialization is preferable when a format can be interpreted in several ways.**

### Inline Profiles

An entry's `profile` may be a registered profile name or an inline dictionary:

```python
entry["profile"] = {
    "reader": {
        "name": "csv",  # replace with the registered reader name
        "args": {"chunk_size": 10000},
    },
}
```

Inline profiles are useful when entries need different reader settings without creating separate YAML files. `ProfileRegistry.resolve()` can also construct an independent copy of a registered profile with overrides:

```python
from fetchez.registry import ProfileRegistry

custom = ProfileRegistry.resolve(
    "csv-default",
    overrides={"chunk_size": 10000},
)
```

This resolves a configuration; it does not register or mutate the original profile. The resolved dictionary can be assigned to an entry's `profile` before stream initialization.

### Discovering Readers and Profiles

```python
from fetchez.api import list_readers, list_profiles, list_data_types

readers = list_readers()
profiles = list_profiles()
data_types = list_data_types()

print(profiles.keys())
```

Reader availability depends on the installed Fetchez packages and extensions. Domain-specific readers (e.g., from Globato) are not necessarily available in a Fetchez-only installation.

## Composing Processing Hooks with `.pipe()`

`.pipe()` accepts a registered hook name, a hook-definition dictionary, or an instantiated hook. It returns the stream, so calls can be chained:

```python
stream = (
    read("observations.csv")
    .pipe("stream-init", profile="csv-default")
    .pipe("my-processing-hook")  # an installed hook
)

for chunk in stream:
    consume(chunk)
```

The example processing hook must be installed and registered. Hook options are supplied directly to that hook, rather than broadcast to all modules or readers.

### Execution Order

Hooks run according to Fetchez pipeline stages, **not** strictly the order in which `.pipe()` is called:

* Manifest hooks run before fetching
* File hooks process acquired files
* Stream hooks operate on streams
* Collection hooks run after file/stream processing

Within stream-stage processing, `stream-init` is prioritized before other stream hooks. See [Hooks & Presets](hooks_and_presets.md) for the full lifecycle.

### Different Profiles for Different Entries

An explicit `.pipe("stream-init", profile=...)` is convenient for a homogeneous group of files. For mixed inputs, entries may instead carry their own profiles, which `get_reader_from_entry()` resolves separately. Do not apply a single specialized profile to unrelated data formats.

Rule-based profile assignment is a planned extension; until it is implemented, use existing entry-producing or manifest-stage configuration to assign entry-specific profiles, or build separate streams when appropriate.

## Example: Domain-Specific Streaming with Globato

Globato extends the Fetchez streaming infrastructure with geospatial elevation readers and processing hooks. For example, a homogeneous collection of ICESat-2 ATL03 files can be processed using an explicitly configured reader:

```python
from globato.api import read

stream = read(
    ["ATL03_a.h5", "ATL03_b.h5"],
    region=[-120, -119, 33, 34],
).pipe(
    "stream-init",
    profile="icesat-atl03",  # use the installed Globato profile name
    classes="1/2/3/6/7/40/41/42",
    append_atl24=True,
)

photons = stream.to_dataframe()
```

This illustrates why explicit reader options belong on `stream-init`: the source list identifies the files, while the reader profile and options determine how the photon data is interpreted. The Globato profile and its options require a compatible Globato installation.

## Developing Custom Readers

Readers decode source files and yield chunks to the streaming pipeline. Fetchez discovers implementations through `ReaderRegistry`; implementations inherit from `fetchez.streams.readers.BaseReader`.

A minimal reader typically provides metadata and a chunk-reading implementation. Depending on the base reader's requirements, it may also implement bounds extraction for spatial indexing:

```python
import numpy as np
from fetchez.streams.readers.base import BaseReader

class MyCustomReader(BaseReader):
    name = "custom-reader"
    meta_extensions = ["dat", "xyz"]

    def _read_chunks(self):
        # Replace with decoding logic for your file format.
        for chunk in decode_my_format(self.src):
            yield chunk

    def _extract_bounds(self, chunk):
        xmin, xmax = np.min(chunk["x"]), np.max(chunk["x"])
        ymin, ymax = np.min(chunk["y"]), np.max(chunk["y"])
        zmin, zmax = np.min(chunk["z"]), np.max(chunk["z"])
        return xmin, xmax, ymin, ymax, zmin, zmax, len(chunk)
```

This is a conceptual skeleton, not a runnable reader: implement `decode_my_format`, confirm the input attribute names against your installed `BaseReader`, and provide any other required methods. Spatial readers can use bounding-box metadata or sidecars to accelerate later spatial operations; the exact behavior depends on the reader implementation.

See the [Contributor Guide](../contribute/index.md) for implementing custom readers.

## Registering Readers, Streams, and Profiles

Installed extensions can provide their own reader classes, stream classes, and YAML profiles. Fetchez discovers these through package entry points:

```toml
[project.entry-points."fetchez.streams"]
my_project = "my_project.streams"

[project.entry-points."fetchez.streams.readers"]
my_project = "my_project.streams.readers"

[project.entry-points."fetchez.streams.profiles"]
my_project = "my_project.streams.profiles"
```

Reader implementations should be Python modules in the reader package; registered profile YAML files should be placed in the profile package. Fetchez also supports user configuration under `~/.fetchez/streams/readers` and `~/.fetchez/streams/profiles`.

A YAML reader profile can describe the selected reader and its default arguments:

```yaml
name: custom-csv
reader:
  name: csv
  args:
    chunk_size: 10000
```

Use the reader name and options supported by your installation. Profiles can be selected by name, resolved with overrides, or supplied inline as entry metadata.

## When to Use Recipes Instead

`read().pipe()` is intended for **lightweight, programmatic streaming**. Choose it when:

* You're building an interactive workflow
* You need a simple data pipeline without YAML configuration
* You're integrating Fetchez into another Python application

Prefer a **Fetchez recipe** when:

* You need persistent YAML configuration for reproducibility
* Your workflow involves complex module/bundle expansion
* You want to use modifiers, schemas, or validation
* You need coordinated multi-region or multi-batch execution

Both interfaces use the same underlying module, hook, and registry ecosystem. Recipes provide persistence and coordination; streams provide flexibility and immediacy.

---

**Next up:** See [Recipes](recipes.md) to learn about composable and reproducible workflows for production use.
