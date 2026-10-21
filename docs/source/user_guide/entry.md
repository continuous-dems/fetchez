# 📝 Pipeline Entries

Fetchez uses **entries** to represent datasets and processing artifacts as they move through a pipeline. An entry is a Python dictionary containing information about a source, its local representation, associated metadata, and any streams or artifacts produced during processing.

Entries provide the common interface between Fetchez modules, readers, and hooks. A module discovers or creates entries, hooks inspect and modify them, readers attach data streams, and downstream operations use their contents to determine what to process.

The entry interface is intentionally lightweight and extensible. Entries remain ordinary Python dictionaries rather than instances of a specialized class, allowing extensions to attach additional information without modifying Fetchez itself.

The `fetchez.entry` module formalizes the common entry vocabulary and provides helpers for validation and identity management.

## Entry basics

A typical entry represents a single dataset discovered by a Fetchez module:

```python
entry = {
    "url": "https://example.org/survey.xyz",
    "dst_fn": "survey.xyz",
    "data_type": "xyz",
}
```

The three standard fields are:

- `url`: The original source location or identifier.
- `dst_fn`: The local filename or path associated with the entry.
- `data_type`: The data type used to identify or process the entry.

These are the minimum fields expected from a normal module-produced entry.

An entry may also carry metadata, a reader profile, processing streams, generated artifacts, and other information needed by subsequent pipeline components.

For example:

```python
entry = {
    "url": "https://example.org/survey.xyz",
    "dst_fn": "survey.xyz",
    "data_type": "xyz",
    "profile": "xyz",
    "src_srs": "EPSG:4326",
    "metadata": {
        "title": "Example elevation survey",
        "survey_id": "survey-123",
    },
    "artifacts": {},
}
```

Not every entry needs every field. Most components only require a subset of the available vocabulary.

## The entry lifecycle

Entries evolve as they pass through a Fetchez pipeline.

A simplified workflow looks like this:

```text
Module
  │
  ├── Discover source datasets
  │       └── Create entries
  │
  ▼
Manifest hooks
  │
  ├── Select, filter, or modify entries
  │
  ▼
Fetch
  │
  ├── Retrieve source files
  │
  ▼
File hooks
  │
  ├── Inspect or process local files
  │
  ▼
Stream hooks
  │
  ├── Attach readers and streams
  ├── Transform data
  └── Produce intermediate artifacts
  │
  ▼
Stream completion and teardown
  │
  ▼
Collection hooks
  │
  ├── Process completed collections
  ├── Select generated artifacts
  └── Produce final outputs
```

The entry itself is passed along the pipeline, allowing information established by one component to be used by later components.

For example, a stream hook may attach a generator to `entry["stream"]`. Another hook may consume or wrap that stream, and a sink may register an output under `entry["artifacts"]`.

The same entry can therefore represent a dataset at several stages of processing without requiring an entirely new object at each stage.

### Entries and modules

Internally, Fetchez commonly passes entries to hooks as `(module, entry)` pairs:

```python
[
    (module_a, entry_a),
    (module_a, entry_b),
    (module_b, entry_c),
]
```

The module reference provides access to module-level configuration, such as its region or other options.

The entry contains information specific to the individual dataset or processing result.

This distinction matters because a single module may produce many entries, while a collection hook may process entries from several modules.

### Entry collections

A hook receives a collection of entries and ordinarily returns a collection:

```python
class ExampleHook(FetchHook):

    def run(self, entries):
        for module, entry in entries:
            entry.setdefault("metadata", {})[
                "processed"
            ] = True

        return entries
```

Hooks may inspect, modify, filter, or generate entries according to their responsibilities.

For hooks that transform a collection, the returned entries become the input to subsequent hooks within the corresponding pipeline stage.

A hook should preserve the expected entry structure and avoid removing fields that downstream components depend on.

## Standard entry fields

Fetchez reserves a common vocabulary through `ENTRY_KEYS` in `fetchez.entry`.

| Field | Description |
|---|---|
| `url` | Original source URL or location |
| `dst_fn` | Local filename or path associated with the entry |
| `data_type` | Dataset or entry data type |
| `profile` | Reader or processing profile |
| `stream` | Active data stream or generator |
| `stream_type` | Type of stream carried by the entry |
| `src_srs` | Source spatial reference system |
| `metadata` | Additional descriptive or processing metadata |
| `artifacts` | Mapping of generated artifact names to output paths |
| `status` | Processing or fetch status |
| `contribution_id` | Optional identity components for processed contributions |

These fields have framework-defined meanings. Extensions should use them consistently rather than introducing alternative names for equivalent concepts.

### Extension-specific fields

Entries are extensible dictionaries, and modules or hooks may introduce additional fields as needed:

```python
entry["survey_quality"] = "reviewed"
entry["custom_processing_flag"] = True
```

Extensions should avoid redefining the meaning of reserved fields.

When possible, descriptive properties should be placed in `metadata`, while generated files should be registered in `artifacts`.

Extension-specific top-level fields are appropriate when they have a distinct pipeline role.

## Streams and artifacts

Two particularly important entry fields are `stream` and `artifacts`.

### Streams

A reader or stream hook may attach an active data stream:

```python
entry["stream"] = reader.yield_chunks()
entry["stream_type"] = "raster-stream"
```

A stream allows large datasets to be processed incrementally rather than loaded entirely into memory.

Stream hooks can consume, transform, or wrap the generator:

```python
def run(self, entries):
    for module, entry in entries:
        if entry.get("stream") is not None:
            entry["stream"] = self.process(
                entry["stream"]
            )

    return entries
```

Streams are transient runtime objects. They should not be treated as stable identifiers or included in serialized cache keys.

### Artifacts

Hooks that produce files can register those outputs in the entry's `artifacts` mapping:

```python
entry.setdefault("artifacts", {})[
    "processed-raster"
] = "/data/processed.tif"
```

This follows Fetchez's artifact convention:

```python
entry["artifacts"][artifact_name] = output_path
```

An artifact may also refer to multiple paths when a hook produces multiple outputs.

Artifacts allow downstream hooks to discover processing results without needing to know how those results were produced.

For example, the `focus-sink` hook can select registered artifacts and create entries that point directly to them:

```yaml
- name: focus-sink
  args:
    target: processed-raster
```

After focusing, subsequent collection hooks receive entries whose `dst_fn` references the selected artifact.

This makes it possible to construct multi-stage workflows where outputs from one operation become inputs to another.

## Entry validation

The `fetchez.entry` module provides lightweight validation helpers.

### `is_entry()`

Checks whether a value is a mapping suitable for use as an entry:

```python
from fetchez.entry import is_entry

assert is_entry({
    "url": "https://example.org/data.xyz"
})
```

This checks the object's general structure, not whether all required fields are present.

The older `entry_p()` name is also available as a compatibility alias.

### `validate_entry()`

Validates an entry against Fetchez's minimum entry contract:

```python
from fetchez.entry import validate_entry

entry = {
    "url": "https://example.org/data.xyz",
    "dst_fn": "data.xyz",
    "data_type": "xyz",
}

validate_entry(entry)
```

With the default `require=True`, validation checks that:

- The entry is a mapping.
- The required `url`, `dst_fn`, and `data_type` keys exist.
- `dst_fn` and `data_type` are nonempty.

Validation raises `TypeError` or `ValueError` when these conditions are not satisfied.

Use `require=False` to check only that the object is a mapping:

```python
validate_entry(entry, require=False)
```

Validation is intentionally lightweight. It does not guarantee that the source exists, that the file is readable, or that arbitrary extension-specific fields are valid.

## Entry and dataset identity

Fetchez provides several functions for identifying entries and datasets.

These functions have different purposes and should not be used interchangeably.

| Function | Purpose |
|---|---|
| `source_id(entry)` | Identify the original source |
| `dataset_id(entry, **kwargs)` | Identify a dataset or processed contribution |
| `entry_id(entry)` | Identify a snapshot of the entry's selected semantic fields |

### Source identity

`source_id()` returns the entry's `url` as its canonical source identifier:

```python
from fetchez.entry import source_id

source = source_id(entry)
```

It requires a nonempty `url` field.

Source identity describes where an entry originated, rather than the particular processing applied to it.

### Dataset identity

`dataset_id()` identifies the underlying dataset using the best available information:

```python
from fetchez.entry import dataset_id

identity = dataset_id(entry)
```

The default resolution order is:

1. Use the entry's `checksum`, if available.
2. Use a non-local source `url`, if available.
3. Use the local filename and file size when `dst_fn` references an existing file.
4. Fall back to `source_id(entry)`.

When no contribution modifiers are present, this behavior preserves the original dataset identity convention.

Dataset identity can be useful for duplicate detection, tracking source contributions, and persistent accumulators.

It is not necessarily a content hash: URLs and filename/size combinations do not guarantee that two files have identical bytes.

### Entry identity

`entry_id()` returns a deterministic SHA-256 hash representing a snapshot of selected semantic entry fields:

```python
from fetchez.entry import entry_id

identity = entry_id(entry)
```

The corresponding `canonical_entry_identity()` function returns the canonical serialized representation used to construct that hash.

The following fields currently participate in entry identity:

- `url`
- `data_type`
- `profile`
- `src_srs`
- `metadata`

Runtime fields such as streams, status, and artifacts are excluded. `dst_fn` and `contribution_id` are not included in the current entry-identity key set.

Because entries are mutable, an entry's identity may change as its semantic fields change during processing.

For example, updating `metadata` may change `entry_id()` even when the underlying dataset remains the same.

For this reason, `entry_id()` is useful for identifying an entry's semantic state, while `dataset_id()` is generally better suited to identifying underlying datasets and their explicitly declared processing contributions.

## Contribution identity

Sometimes the same underlying dataset contributes to a pipeline in several different ways.

For example, a dataset might be:

- Processed with different weights.
- Transformed into a different spatial reference system.
- Filtered using different quality-control settings.
- Converted into different derived products.
- Reprocessed using an updated algorithm.

These products may originate from the same dataset but should not always be treated as identical contributions.

Fetchez supports this distinction through the optional `contribution_id` field and keyword arguments to `dataset_id()`.

### Registering a contribution

A processing hook may add a named contribution identity:

```python
entry.setdefault("contribution_id", {})[
    "quality_filter"
] = "filter-v2"
```

Fetchez also provides a convenience helper:

```python
from fetchez.entry import set_contribution_id

set_contribution_id(
    entry,
    "quality_filter",
    "filter-v2",
)
```

The helper creates the `contribution_id` mapping if necessary and assigns the named value.

Multiple hooks can contribute independent identity components:

```python
set_contribution_id(
    entry,
    "vertical_transform",
    "transform-abc123",
)

set_contribution_id(
    entry,
    "quality_filter",
    "filter-def456",
)
```

The resulting entry contains:

```python
{
    "contribution_id": {
        "vertical_transform": "transform-abc123",
        "quality_filter": "filter-def456",
    }
}
```

Each hook can update its own component without overwriting another hook's contribution identity.

Contribution mappings are canonicalized during identity generation, so dictionary insertion order does not affect the resulting identifier.

A hook that may run multiple times should use distinct component names when earlier processing steps must remain part of the identity.

### Consumer-specific parameters

A downstream consumer may also provide parameters that affect how the dataset contributes to a result:

```python
identity = dataset_id(
    entry,
    weight=2.0,
)
```

This is especially useful for accumulation and merging operations.

For example:

```python
dataset_id(entry, weight=1.0)
dataset_id(entry, weight=2.0)
```

These produce different identifiers for the same underlying dataset because the consumer-specific parameters differ.

Keyword arguments and upstream `contribution_id` components are combined deterministically.

The two namespaces remain separate, avoiding collisions between hook-provided contributions and consumer-supplied parameters.

### Generated identifiers

When either `contribution_id` or keyword arguments are provided, `dataset_id()` constructs a deterministic hash of those modifiers and appends its first 16 hexadecimal characters to the base dataset identity.

Conceptually:

```text
<base-dataset-id>|<modifier-digest>
```

The exact identifier is intended for programmatic comparison rather than as a user-facing description.

When neither a nonempty contribution mapping nor keyword arguments are supplied, `dataset_id()` returns the original base identifier without a modifier suffix.

### When should a hook update contribution identity?

Hooks should register a new contribution identity when they materially change what the dataset contributes to downstream processing.

Typical examples include changes to:

- Measurements or data values.
- Weights or uncertainties.
- Coordinate or datum transformations.
- Data selection or quality filtering.
- Derived source products.

Hooks that only modify logging, descriptive metadata, presentation, or other non-data-affecting properties generally should not change contribution identity.

Contribution values should be deterministic and serializable. Strings, numeric values, lists, and dictionaries are suitable when their contents are stable.

Avoid temporary filenames, memory addresses, open objects, or other values that may change between equivalent executions.

The identity generator canonicalizes common Python types and rejects unsupported values in contribution modifiers.

### Contribution identity and caching

Contribution identities are useful for cache management and incremental processing, but they are not themselves a complete cache-validation system.

A matching identity means the dataset and declared modifiers are equivalent according to the identity rules. It does not prove that an existing artifact is current or uncorrupted.

Likewise, generating a new contribution identity does not automatically remove an earlier contribution from an accumulated result.

Persistent accumulators must separately define whether contributions can be appended, replaced, or rebuilt.

## Entry identity versus contribution identity

Consider an elevation dataset processed by two different quality-control configurations:

```python
entry = {
    "url": "https://example.org/survey.xyz",
    "dst_fn": "survey.xyz",
    "data_type": "xyz",
    "metadata": {
        "title": "Example survey",
    },
}
```

The underlying dataset is unchanged:

```python
base = dataset_id(entry)
```

After processing, a filter registers its identity:

```python
set_contribution_id(
    entry,
    "survey_qc",
    "qc-configuration-a",
)

filtered_a = dataset_id(entry)
```

A second processing configuration produces a different contribution:

```python
set_contribution_id(
    entry,
    "survey_qc",
    "qc-configuration-b",
)

filtered_b = dataset_id(entry)

assert filtered_a != filtered_b
```

Meanwhile, changing descriptive metadata does not change dataset identity:

```python
before = dataset_id(entry)

entry["metadata"]["title"] = "Updated survey title"

assert dataset_id(entry) == before
```

But because `metadata` participates in entry identity, such a change can affect `entry_id()`.

This separation allows Fetchez components to choose the appropriate identity for their purpose.

## Writing hooks that work with entries

Custom hooks should follow a few general conventions when working with entries.

### Preserve existing fields

Avoid replacing entries unnecessarily when only a small modification is required.

Prefer:

```python
entry.setdefault("metadata", {})[
    "processed"
] = True
```

over constructing an entirely new entry that discards the original fields.

When a hook intentionally creates a new derived entry, preserve the relevant source information and metadata needed by downstream components.

### Register output artifacts

When a hook generates a file:

```python
entry.setdefault("artifacts", {})[
    self.name
] = output_path
```

This makes the output discoverable through the standard artifact protocol.

### Use the common identity helpers

Instead of implementing custom source identity logic:

```python
identity = dataset_id(
    entry,
    weight=module.weight,
)
```

If a hook materially changes the contribution, register an explicit component:

```python
set_contribution_id(
    entry,
    self.name,
    processing_hash,
)
```

This keeps identity conventions consistent between Fetchez and its extensions.

### Keep transient objects out of persistent identities

Entries may contain streams, generators, handles, temporary artifacts, and other runtime information.

These should not be used as persistent identities.

Use stable source identifiers, processing parameters, and explicit contribution components instead.

## Best practices

When developing modules or hooks, keep the following principles in mind:

1. **Use standard fields first.** Prefer Fetchez's defined entry vocabulary over inventing equivalent extension-specific fields.
2. **Preserve source identity.** Retain enough information to identify where an entry originated, even when it represents a derived artifact.
3. **Keep metadata and artifacts separate.** Use `metadata` for descriptive information and `artifacts` for generated outputs.
4. **Treat entries as mutable pipeline state.** Don't assume `entry_id()` remains unchanged throughout processing.
5. **Declare meaningful contribution changes.** Use `contribution_id` when processing changes the data seen by downstream consumers.
6. **Avoid unnecessary identity changes.** Descriptive or diagnostic updates should not invalidate otherwise equivalent dataset contributions.
7. **Use deterministic identity components.** Equivalent processing should generate equivalent identifiers across repeated runs.
8. **Handle persistent state explicitly.** Identity changes do not automatically invalidate or replace previously accumulated data.

## API reference

The principal entry helpers are provided by `fetchez.entry`:

```python
from fetchez.entry import (
    ENTRY_KEYS,
    REQUIRED_ENTRY_KEYS,
    ENTRY_RUNTIME_KEYS,
    ENTRY_IDENTITY_KEYS,
    is_entry,
    validate_entry,
    canonical_entry_identity,
    entry_id,
    source_id,
    dataset_id,
    set_contribution_id,
)
```

| Helper | Description |
|---|---|
| `is_entry(value)` | Check whether a value is a mapping |
| `entry_p(value)` | Backward-compatible alias for `is_entry()` |
| `validate_entry(entry, require=True)` | Validate the basic entry contract |
| `canonical_entry_identity(entry)` | Serialize the entry's selected semantic fields deterministically |
| `entry_id(entry)` | Hash the canonical semantic entry snapshot |
| `source_id(entry)` | Return the canonical source identifier |
| `dataset_id(entry, **kwargs)` | Return a dataset identity incorporating optional contribution modifiers |
| `set_contribution_id(entry, name, value)` | Add or replace a named contribution identity component |

Entries are deliberately simple. Most modules and hooks can work directly with ordinary dictionaries, using these helpers only when they need validation or consistent identity management.

The entry contract is intended to provide a stable common vocabulary while preserving the flexibility that allows Fetchez and its extensions to define new processing capabilities without changes to the core framework.
