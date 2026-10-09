# Set Entry (`set-entry`)

`set-entry` is a manifest-stage hook that assigns an arbitrary field on Fetchez entries. It is useful for assigning reader profiles, correcting data types, adding source metadata, or setting extension-specific fields before file and stream processing.

## Usage

Set a profile for matching HDF5 files:

```python
stream = fetchez.read(["ATL03_a.h5", "elevation.tif"]).pipe(
    "set-entry", key="profile", match="ATL03_*.h5", value="icesat-atl03"
)
```

Choose profiles for multiple formats (profile names are examples and must be registered):

```python
stream = fetchez.read(sources).pipe(
    "set-entry",
    key="profile",
    rules={"*.h5": "icesat-atl03", "*.tif": "rasterio"},
).pipe("stream-init")
```

Set a full inline profile for selected entries:

```python
stream = fetchez.read(sources).pipe(
    "set-entry", key="profile", match="ATL03_*.h5",
    value={
        "reader": {
            "name": "atl03",
            "args": {"classes": "1/2/3/6/7/40/41/42"},
        }
    },
)
```

The reader must be registered; `set-entry` only assigns the value. `stream-init` subsequently resolves the profile and initializes the reader.

## Arguments

| Argument | Meaning |
| --- | --- |
| `key` | Required destination entry field (e.g. `profile`, `data_type`, `src_srs`). |
| `value` | Value to assign for a matching `match` pattern, or unconditionally when no rules/match are given. |
| `match` | Optional single glob pattern tested against `match_key`. |
| `match_key` | Entry field to inspect; default `dst_fn`. Special value `module` uses the producing module's registered name. |
| `rules` | Ordered mapping of glob patterns to assigned values. First matching rule wins. |
| `default` | Fallback assigned when no pattern matches. |
| `overwrite` | Whether to replace an existing non-`None` value; default `False`. |
| `match_mode` | `glob` (default) or `substring` for compatibility use. |

Matching is case-insensitive. For `dst_fn`, patterns are tested against both the full path and the basename. `*.h5` matches HDF5 filenames; `ATL03_*.h5` can narrow the selection. A `.h5` extension alone does not prove the file contains ATL03 data.

### Match by module or entry metadata

```python
stream.pipe(
    "set-entry", key="profile", match_key="module",
    rules={"icesat2": "icesat-atl03"},
)

stream.pipe(
    "set-entry", key="src_srs", match_key="data_type",
    rules={"xyz": "EPSG:26911"},
)
```

### Set arbitrary metadata

```python
stream.pipe("set-entry", key="processing_tag", value="reviewed")
```

Values are deep-copied for each entry so inline profile dictionaries and other mutable metadata are not shared between entries.

## Execution and compatibility

`set-entry` runs at the **manifest** stage, before stream initialization. It changes only the requested entry field; it does not inspect file contents, resolve reader profiles, or validate data-type compatibility. By default, it preserves existing non-`None` values. Set `overwrite=True` to replace them.

Existing `set-datatype` hooks remain available and retain their historical substring-based matching and argument syntax. This hook is the generic alternative for new workflows; migrating existing recipes is optional.

See [Hooks and Presets](../hooks_and_presets.md) and [Streams](../streams.md) for the pipeline lifecycle and `.pipe()` usage.
