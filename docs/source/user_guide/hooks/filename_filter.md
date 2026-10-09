# Filename filter

`filename-filter` selects entries by the basename of their `dst_fn` path. Use it
to keep a subset of a module's results, such as elevation TIFFs while excluding
preview images, before passing them to later hooks. The aliases
`filename_filter` and `fn_filter` refer to the same hook.

## Configuration

| Argument | Default | Behavior |
| --- | --- | --- |
| `match` | `None` | Keep only filenames containing this string. An omitted or empty value imposes no inclusion requirement. |
| `exclude` | `None` | Discard filenames containing this string, including files that satisfy `match`. An omitted or empty value excludes nothing. |
| `regex` | `False` | Interpret both patterns as Python regular expressions, using `re.search`. |
| `stage` | `file` | Filter after download by default. Use `manifest` to filter the results before downloading them; `pre` is an alias for `manifest`. |

Both patterns are case-sensitive unless a regular expression explicitly changes
that behavior, for example `(?i)\.tif$`. Plain `match=.tif` is a substring test,
so it also matches `tile.tif.aux.xml`. For an extension match, use
`match=\.tiff?$` with `regex=True`. Invalid regular expressions raise `re.error`
when evaluated; the hook does not convert them to literal strings.

Filtering uses only the filename, not its parent directory, entry URL, file
contents, or data type. With no patterns set, every entry is retained. A missing
`dst_fn` is treated as an empty filename.

## CLI example

Inspect the registered hook and its arguments:

```bash
fetchez hooks info filename-filter
```

To attach it to a source, use the comma-separated hook arguments accepted by
`fetchez build`. This example exports a recipe without downloading any data:

```bash
fetchez build --export filtered-tiles.yaml tnm \
  --hook "filename-filter:match=.tif,exclude=preview,stage=manifest"
```

Before running the exported recipe, configure the source's region and dataset
for the data you need. `stage=manifest` prevents rejected results from being
downloaded. The default `file` stage instead filters entries that have already
been downloaded; it does not delete their files.

## Local Python example

This example operates on destination-path metadata. It needs no network access,
credentials, or actual TIFF files:

```python
from pathlib import Path

from fetchez.hooks.fn_filter import FilenameFilter

entries = [
    {"dst_fn": str(Path("tiles") / "elevation_01.tif")},
    {"dst_fn": str(Path("tiles") / "elevation_preview.tif")},
    {"dst_fn": str(Path("tiles") / "elevation_02.tif.aux.xml")},
    {"dst_fn": str(Path("tiles") / "elevation_03.TIFF")},
]

hook = FilenameFilter(match=r"(?i)\.tiff?$", exclude="preview", regex=True)
selected = hook.run(entries)

assert [Path(entry["dst_fn"]).name for entry in selected] == [
    "elevation_01.tif",
    "elevation_03.TIFF",
]
assert selected[0] is entries[0]
assert len(entries) == 4
```

The extension pattern keeps both TIFF suffixes regardless of case, while the
separate `preview` exclusion removes the preview. The `.aux.xml` sidecar fails
the end-of-filename match.

## Inputs, outputs, and limitations

The pipeline supplies a list of `(module, entry)` tuples. Direct Python callers
can also pass entry dictionaries, as above. The hook returns a new list of the
retained items in their original order. It preserves the original tuple and
entry objects and does not add metadata fields or read, rename, or delete files.

Choose the stage based on the filenames available at that point. Manifest
filtering examines the planned destination names, so it cannot select individual
members of an archive that has not yet been extracted. For that workflow, put
`unzip` before `filename-filter` in the file-stage hook chain so the filter sees
the extracted entries.

The hook has no optional dependencies beyond a normal Fetchez installation.
Its matching uses Python's standard-library `os.path` and `re` modules.

See [Hooks and Presets](../hooks_and_presets.md) for hook ordering, stages, and
reusable configurations, or the [Hook Reference](index.md) for other documented
hooks.
