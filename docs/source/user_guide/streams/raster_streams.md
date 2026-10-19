# Raster streams and raster processing

Fetchez provides generic, windowed raster processing through three complementary components:

- **`RasterReader`** reads raster datasets into a `raster-stream` of chunk dictionaries.
- **`RasterHook`** is a small base class for transformations of individual chunks.
- **`RasterWrite`** materializes a raster-stream as a GeoTIFF, either as a terminal operation or an inline tap.

**`RasterPipeline`** composes those components to operate on *files* at the `file` or `collection` stage. It is useful for preprocessing source rasters before a domain-specific reader, and postprocessing completed raster products. An ordinary raster hook does not open files or write them itself.

```text
Raster file
    |
    v
RasterReader (windowing + pixel reads)
    |
    v
raster-stream: chunk dictionaries + shared RasterContext
    |
    +--> RasterHook A --> RasterHook B --> RasterWrite
    |                                          |
    |                                          v
    |                                      GeoTIFF
    +--> domain-specific stream consumer / adapter
```

Each hook receives the **current, already-processed chunk** produced by the previous hook. The stream does **not** reread source pixels between hooks. `RasterContext` holds shared raster-level metadata.

## Reading rasters

The generic implementation is `fetchez.streams.readers.raster.RasterReader` (registered reader name: `rasterio`). It reads windowed arrays eagerly using Rasterio. For example:

```python
from fetchez.streams.readers.raster import RasterReader

reader = RasterReader(
    "input.tif",
    chunk_size=512,
    buffer=8,
    bands=(1, 2, 3),
    band_mode="stack",
)

for chunk in reader.yield_chunks():
    data = chunk["data"]
    window = chunk["window"]
    context = chunk["context"]
    print(window, data.shape, context.profile["count"])
```

### Reader options

| Option | Meaning |
| --- | --- |
| `path` | Raster filename or Rasterio/GDAL-readable path. |
| `chunk_size=None` | Use native raster blocks, with an optimization for strip-organized rasters. |
| `chunk_size=512` | Read nominally 512 x 512 core windows. Edge windows can be smaller. |
| `chunk_size=(256, 1024)` | Read rectangular core windows as `(height, width)`. |
| `chunk_size="full"` or `-1` | Produce one core window for the **selected region**. Can use substantial memory. |
| `buffer=0` | Extra pixels (halo) around each core window; clipped to source bounds. |
| `region=...` | Limit output to a selected region, transformed to the raster's horizontal CRS when necessary. |
| `bands=None` | Read all raster bands, or pass an ordered sequence of **1-based** band indices. |
| `band_mode="stack"` | Emit one 3-D array per window: `(bands, rows, cols)`. Recommended for multiband output. |
| `band_mode="single"` | Emit a separate 2-D array for each selected band and window. |
| `include_mask=True` | Include Rasterio validity-mask arrays in each chunk. |
| `src_srs=...` | Override the source CRS used by the reader's spatial handling; see implementation for vertical suffix handling. |
| `path_prefix`, `path_suffix` | Construct the Rasterio input path around `path` (for example GDAL VSI prefixes). |

**Important:** `chunk_size="full"` still reads all selected pixels into NumPy memory; it does not enable deferred access. At present `RasterContext` exposes **metadata only**; deferred reads, write-back, and raw dataset handles are not supported.

## The raster-stream chunk contract

A raster stream yields ordinary Python dictionaries. Every chunk references the **same context object** for its input raster.

### Common chunk fields

| Key | Type / meaning | Notes |
| --- | --- | --- |
| `context` | `RasterContext` | Shared across all chunks of a raster. |
| `data` | NumPy array | **Current pipeline pixel values**. Stacked: `(bands, rows, cols)`; single-band: `(rows, cols)`. Includes halo pixels if buffering is enabled. |
| `window` | `rasterio.windows.Window` | **Core** window in *source dataset pixel coordinates*; the non-overlapping region to retain in output. |
| `read_window` | `Window` | Actual sampled window (core plus any available halo), also source-relative. |
| `transform` | Affine transform | Transform for `data` / `read_window`, **not necessarily** the core `window`. |
| `crs` | Rasterio CRS | CRS used by the reader for its spatial operations. |
| `mask` | NumPy validity mask, optional | Present only when `include_mask=True`; follows the shape of `data`. Rasterio mask values are generally 0 for invalid and nonzero for valid. |

### Additional fields by band mode

| Mode | Keys | Shape / semantics |
| --- | --- | --- |
| `stack` | `band_indices` | Tuple of selected **source** band numbers, in output order. |
| `stack` | `nodata` | Tuple of nodata values corresponding to `band_indices`. |
| `stack` | `band_units` | Tuple of unit strings (or `None`). |
| `stack` | `band_descriptions` | Tuple of band descriptions (or `None`). |
| `single` | `band_index` | Source band number for this chunk. |
| `single` | `nodata` | Scalar nodata value for this band. |

With no buffering, `read_window == window`. With buffering, `data` can be larger than `window`; writers must crop the halo before writing. Hooks should use `chunk["transform"]` when interpreting coordinates of the **actual array**.

### Core and buffered windows

```text
+--------------------------------+
|           read_window          |
|    +----------------------+    |
|    |        window        |    |
|    |     output core      |    |
|    +----------------------+    |
|         halo / buffer          |
+--------------------------------+
```

For a core window starting at `(col=100, row=200)` with a buffer of 8, the read window may start at `(92, 192)`. At image boundaries the halo is clipped. Therefore **never assume the core starts at `data[:, 8, 8]`**; calculate offsets from the two windows:

```python
core = chunk["window"]
read = chunk["read_window"]
y0 = int(core.row_off - read.row_off)
x0 = int(core.col_off - read.col_off)
h, w = int(core.height), int(core.width)

array = chunk["data"]
core_data = (
    array[:, y0:y0+h, x0:x0+w]
    if array.ndim == 3 else array[y0:y0+h, x0:x0+w]
)
```

Usually **hooks should process the buffered array and preserve the window metadata**, leaving halo trimming to `RasterWrite`.

### Shared `RasterContext`

`RasterContext` currently exposes these properties:

```python
context = chunk["context"]
context.source_profile  # Original Rasterio dataset profile (copy)
context.profile         # Current output-grid/profile description (copy at creation)
context.source          # Original dataset path/name
context.metadata        # Extensible dictionary; initially contains:
                        #   "tags": dataset-level tags
                        #   "selection_window": selected source-grid window
```

`source_profile` describes the opened dataset. `profile` describes the selected region and band count for downstream output. For example, cropping changes `profile["width"]`, `profile["height"]`, and `profile["transform"]`. Selecting two stacked bands changes `profile["count"]` to 2.

The context is shared, so **do not store per-chunk scratch arrays in `context.metadata`**. Hooks that change dataset-wide output characteristics may need to update `context.profile` consistently *before* affected chunks are written. The current base does not implement a separate profile-transformation lifecycle; treat grid-changing operations as advanced work requiring explicit validation.

## Writing a custom raster hook

Subclass `fetchez.hooks.rasters.RasterHook` and implement **only** `process_chunk(chunk, entry)`. The base wraps existing streams lazily, preserves hook ordering, and checks `entry["stream_type"] == "raster-stream"` when a stream is present.

```python
import numpy as np
from fetchez.hooks.raster import RasterHook


class RasterClamp(RasterHook):
    name = "raster-clamp"
    meta_desc = "Clamp valid raster cells to an optional range."

    def __init__(self, lower=None, upper=None, **kwargs):
        super().__init__(**kwargs)
        self.lower = lower
        self.upper = upper

    def process_chunk(self, chunk, entry):
        data = chunk["data"].copy()
        mask = chunk.get("mask")

        if mask is not None:
            valid = mask != 0
        else:
            valid = np.isfinite(data) if np.issubdtype(data.dtype, np.floating) else np.ones(data.shape, dtype=bool)
            ndv = chunk.get("nodata")
            if not isinstance(ndv, tuple) and ndv is not None:
                valid &= data != ndv
            # For stacked rasters with per-band nodata, handle each band
            # separately (or enable include_mask=True in RasterReader).

        if self.lower is not None:
            data[valid] = np.maximum(data[valid], self.lower)
        if self.upper is not None:
            data[valid] = np.minimum(data[valid], self.upper)

        return {**chunk, "data": data}
```

### Hook authoring rules

- **Operate on upstream `chunk["data"]`**, not by reopening the original raster; that preserves the result of earlier hooks.
- Return a **chunk dictionary**. Return `None` only when you deliberately want to suppress the whole chunk; a missing chunk may leave unwritten cells in a downstream fixed-grid raster.
- Prefer **copy-on-write** if changing arrays, particularly when a chunk may be reused or inspected elsewhere.
- Preserve `context`, `window`, `read_window`, `transform`, and `crs` for grid-preserving operations.
- Keep `data`, `mask`, band metadata, and `context.profile` mutually consistent if changing their interpretation.
- For neighborhood algorithms, request sufficient reader `buffer`. Chaining neighborhood operations may require a larger combined halo or an explicit intermediate write/re-read boundary to avoid seams.
- A `RasterHook` does **not** initialize streams or write files. Entries with no stream are passed through; entries with an incompatible declared stream type raise an error.

The base advertises `meta_stage="stream"`, `meta_accepts="raster-stream"`, and `meta_produces="raster-stream"`. These describe the **internal stream** even when a composite pipeline runs the hook at another lifecycle stage.

## Writing raster streams to files

Use `fetchez.hooks.rasters.raster_writer.RasterWrite` (`raster-write`). It reads the **first chunk** to obtain `chunk["context"].profile`, then processes that first chunk along with the remainder of the stream. No chunk is lost.

```python
from fetchez.hooks.rasters.raster_writer import RasterWrite

entry = {
    "dst_fn": "input.tif",
    "stream_type": "raster-stream",
    "stream": RasterReader("input.tif", chunk_size=512).yield_chunks(),
}
RasterWrite(suffix="_processed", drain=True).run([(None, entry)])
print(entry["dst_fn"])  # Absolute path ending in input_processed.tif
```

(Import `RasterReader` as shown in the earlier example.)

### Writer settings and behavior

| Argument | Behavior |
| --- | --- |
| `drain=True` | Consume the entire stream **now**, write the file, remove `stream` and `stream_type`, and update `entry["dst_fn"]`. Suitable for terminal output or `RasterPipeline`. |
| `drain=False` (default) | Replace `entry["stream"]` with an **inline tap** that writes while yielding unchanged chunks onward. No output is published unless the stream is fully consumed. |
| `suffix="_final"` | Default per-source output name: `<stem>_final.tif`. |
| `output_path` | A directory (existing path or one ending in `/`), a single explicit filename (one entry only), or a template containing `{stem}`, `{name}`, `{suffix}`, `{index}`. |
| `artifact_id` | Key under `entry["artifacts"]` (default `raster-write`) once output is successfully published. |

Example per-file output naming:

```python
RasterWrite(
    output_path="processed/{stem}_cleaned.tif",
    drain=True,
)
```

`RasterWrite` creates output directories, writes through a temporary file, and publishes the final file only after successful stream exhaustion. It refuses to overwrite the original source path. It trims halos and maps **source-relative** core windows to the output-relative grid using `context.metadata["selection_window"]`.

For stacked multiband chunks, source band indices are mapped to consecutive destination bands in the selected order. Dataset-level tags, band descriptions, and units are written; Rasterio profile fields (including shared nodata when present) control dataset creation. **Arbitrary per-band tags are not currently copied.** The single-band mode currently has a one-band output profile; use `band_mode="stack"` for normal multiband writing.

> **Inline lifecycle:** an inline writer produces a completed file only if a downstream consumer exhausts the stream. If an iterator is abandoned early, the temporary file is cleaned up when the generator is closed/finalized; no completed artifact should be assumed.

## Processing raster *files* with `RasterPipeline`

`fetchez.hooks.rasters.raster_pipeline.RasterPipeline` (`raster-pipeline`) is an **ordinary composite `FetchHook`** that runs its own ordered mini-pipeline:

```text
file entry (`dst_fn`)
    -> RasterReader
    -> zero or more RasterHook implementations
    -> RasterWrite(drain=True)
    -> updated file entry (`dst_fn`)
```

Unlike ordinary raster hooks, the composite can be assigned to **`file` or `collection`** stage. Its nested hooks still consume `raster-stream` chunks; they run *inside the composite*, not as separately scheduled stream-stage hooks. The outer `run_fetchez()` scheduler does not need to be changed.

### File-stage preprocessing

The following is a **hook configuration fragment** to place in a module's hook list or another appropriate recipe hook list:

```yaml
- name: raster-pipeline
  stage: file
  args:
    reader:
      chunk_size: 512
      buffer: 8
      band_mode: stack
    hooks:
      - name: raster-clamp
        args:
          lower: -1000
      - name: raster-smooth
        args:
          sigma: 2
    writer:
      suffix: _processed
```

`raster-clamp` and `raster-smooth` above are **example plugin names**; they must be registered in your environment, and must accept/produce `raster-stream`. Choose the buffer based on the actual neighborhood requirements of your hooks.

This runs after acquisition, before Fetchez's ordinary stream stage. The resulting `dst_fn` points to the processed raster, so an extension such as Globato can subsequently initialize its domain-specific point stream from it.

### Collection-stage postprocessing

```yaml
- name: raster-pipeline
  stage: collection
  args:
    reader:
      chunk_size: 1024
    hooks:
      - name: raster-clamp
        args:
          lower: -5000
    writer:
      output_path: "processed/{stem}_final.tif"
```

Collection hooks run after the ordinary stream stage, so this form is appropriate for raster files **already materialized** by a preceding operation (for example, generated DEMs). The composite does not itself combine multiple raster files or create mosaics; it processes **one output per input file entry**.

### Composite options

| Option | Behavior |
| --- | --- |
| `hooks` | Ordered nested hooks: registry names, `{name, args}` mappings, Python hook classes, or instances. |
| `reader` | Keyword arguments for each `RasterReader`; input `path` is supplied from that entry's `dst_fn`. |
| `writer` | Keyword arguments for `RasterWrite`, except the composite **forces `drain=True`**. |
| `stage` | `file` (default) or `collection`; other stages are rejected. |
| `skip_non_raster=True` | Pass through entries whose `data_type` indicates another type or whose untyped extension is not recognized as raster. |

The composite identifies raster entries explicitly labeled `data_type="raster"` or, if `data_type` is absent, by selected common raster filename extensions. It requires a usable `dst_fn` and **no active `entry["stream"]`**. Nested hooks must preserve the entries' identities and order; the composite does not currently support splitting, merging, or changing the number of entries. It instantiates registry-resolved nested hooks and tears down those instances after processing.

### Python usage without the full scheduler

```python
from fetchez.hooks.rasters.raster_pipeline import RasterPipeline

entry = {"dst_fn": "input.tif", "data_type": "raster"}
pipeline = RasterPipeline(
    stage="file",
    reader={"chunk_size": 512, "buffer": 4},
    hooks=[{"name": "raster-clamp", "args": {"lower": -1000}}],
    writer={"suffix": "_filtered"},
)

pipeline.run([(None, entry)])
print(entry["dst_fn"])
```

The composite updates the existing entry and returns the usual `(module, entry)` pairs; actual registered hook names must be available through `HookRegistry`.

## Workflow stages: which approach should I use?

| Goal | Recommended approach |
| --- | --- |
| Transform an already-active raster stream | Add ordinary `RasterHook` implementations in the `stream` stage. |
| Write the current stream and continue downstream | `RasterWrite(drain=False)` as an inline tap. |
| Finish a stream and materialize output | `RasterWrite(drain=True)`. |
| Transform downloaded raster files before a domain reader | `RasterPipeline(stage="file")`. |
| Postprocess completed raster artifacts | `RasterPipeline(stage="collection")`. |
| Package a repeated configuration for users | A **preset** containing appropriate hook definitions. |
| Translate legacy stage-assigned Globato hooks | A **modifier** can eventually rewrite them into composite pipelines; this compatibility modifier is **not** part of the components documented here. |

The architectural distinction is **composite hook for execution, preset for reusable configurations, modifier for legacy compatibility**.

## Limitations and compatibility notes

1. **Eager pixel access:** reading creates NumPy arrays, including masks when requested. A `"full"` window can be expensive. There is no public deferred read or write-back interface yet.
2. **Source windows vs. output grid:** `window` and `read_window` refer to source pixel coordinates; the writer adjusts them using `selection_window`. Avoid treating these as output-relative coordinates in custom writers.
3. **Stream ownership:** ordinary raster hooks are lazy; `RasterPipeline` deliberately drains the writer before returning. A composite cannot receive an entry with an active stream.
4. **Chained neighborhood filters:** buffering each original input window is not a general replacement for reading neighboring *already-processed* windows. Watch for seams; materialize/re-read or account for combined halos where necessary.
5. **Band/profile changes:** the standard writer supports the current stacked representation and selected band order. Grid-changing hooks, band-count changes, and multi-band writes from separately emitted single-band chunks need additional coordination.
6. **Nodata and masking:** `mask` comes from Rasterio's validity masks. Hooks must update it if they change validity; nodata values and data types must remain consistent with output profiles.
7. **Metadata:** the writer preserves dataset tags, band descriptions, and units where provided, but not arbitrary per-band tags. Do not assume all source metadata survives format-changing operations.
8. **Collision avoidance:** the writer checks duplicate destinations within one call; coordinate output names across separate calls or concurrent pipelines yourself. Its file publication is atomic on the same filesystem, but it is not a cross-process transaction manager.
9. **Execution-stage semantics:** the composite's **outer** stage determines when it runs; nested hooks run synchronously in the composite's own order. This behavior is distinct from placing those nested hooks directly in the outer `run_fetchez()` hook list.

## Code locations

The current implementations are expected at:

```text
fetchez/streams/readers/raster.py        # RasterReader + RasterContext
fetchez/hooks/rasters/base.py            # RasterHook base
fetchez/hooks/rasters/raster_writer.py   # RasterWrite
fetchez/hooks/rasters/raster_pipeline.py # RasterPipeline
```
