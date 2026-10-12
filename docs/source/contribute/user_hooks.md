# 🪝 Developing User Hooks
Hooks allow you to inject custom processing into the `fetchez` pipeline. You can write hooks to process files immediately after they are downloaded, or to run setup/teardown tasks.

## How it Works

`fetchez` scans `~/.fetchez/hooks/` at runtime.

It registers any class that inherits from `fetchez.hooks.FetchHook`.

## Example Hook
Create a file named `~/.fetchez/hooks/audit_log.py` to log every download to a file:

```python
import os
from fetchez.hooks import FetchHook


class AuditLog(FetchHook):
    # This name is used in the CLI: --hook audit
    name = "audit"
    meta_desc = "Log downloaded files to audit.txt"
    meta_stage = 'file'  # Runs per-file

    def run(self, entries):
        # Hooks receive a list of entries: [{url, path, type, status}, ...]
        for entry in entries:
            url = entry.get('url')
            path = entry.get('dst_fn')
            status = entry.get('status')

            if status == 0:
                with open("audit.txt", "a") as f:
                    f.write(f"DOWNLOADED: {path} FROM {url}\n")

        # Always return the entries so the pipeline continues!
        return entries
```

## Hook Metadata and Capabilities

Hooks can declare metadata describing what they do, what they operate on, and which other components they may need. Fetchez uses this information for registry discovery, documentation, and, where supported, compatibility validation.

Every hook already receives and returns collections of `(module, entry)` pairs through `run(entries)`. You do not need to declare `entry` as an accepted or produced type.

### Metadata vocabulary

| Field             | Purpose                                                                       |
|-------------------|-------------------------------------------------------------------------------|
| `meta_desc`       | Short, human-readable description of the hook.                                |
| `meta_stage`      | Default execution stage (`manifest`, `file`, `stream`, or `collection`).      |
| `meta_category`   | Broad functional grouping for discovery.                                      |
| `meta_effects`    | Operations performed, such as filtering entries or creating artifacts.        |
| `meta_accepts`    | Stream types accepted by the hook, when it operates on streams.               |
| `meta_produces`   | Stream type produced by the hook, when it transforms a stream representation. |
| `meta_requires`   | Required companion hooks, including their scope and stage when applicable.    |
| `meta_data_types` | Artifact data types the hook is designed to process (informational).          |
| `meta_related`    | Other useful or complementary components.                                     |

All fields are optional. Omitted metadata means *unspecified*, not necessarily unsupported.

### Describing hook effects

Use `meta_effects` to describe what your hook changes or creates. A hook may declare multiple effects.

Suggested initial vocabulary:

| Effect              | Meaning                                                                 |
|---------------------|-------------------------------------------------------------------------|
| `filters-entries`   | Selects or removes entries from processing.                             |
| `modifies-entries`  | Changes entry metadata or properties.                                   |
| `creates-entries`   | Creates additional independently processable entries.                   |
| `modifies-artifact` | Changes an existing file or artifact.                                   |
| `creates-artifact`  | Generates a new file or persistent artifact.                            |
| `creates-stream`    | Initializes a stream from an entry.                                     |
| `filters-chunks`    | Filters records or chunks within a stream.                              |
| `transforms-stream` | Changes a stream's representation.                                      |
| `consumes-stream`   | Consumes or observes streamed data, potentially producing side effects. |

For example, an extraction hook might declare:

```python
meta_stage = "file"
meta_effects = ["creates-entries", "creates-artifact"]
```

A generic filename filter might declare:

```python
meta_stage = "manifest"
meta_effects = ["filters-entries"]
```

Effects describe capabilities, not mandatory outcomes. For example, an extraction hook may produce no new entries when an archive is empty.

### Stream compatibility

For hooks that operate on streamed chunks, `meta_accepts` and `meta_produces` describe stream representations, not artifact data types.

```python
class RasterToPoints(FetchHook):
    name = "raster-to-points"
    meta_stage = "stream"
    meta_accepts = ["raster-stream"]
    meta_produces = "point-stream"
    meta_effects = ["transforms-stream"]
```

A hook that filters a stream without changing its representation may omit `meta_produces`:

```python
meta_accepts = ["point-stream"]
meta_effects = ["filters-chunks"]
```

Use `meta_produces` only when the output representation is known. For example, `stream-init` initializes a stream, but its output type depends on the selected reader, so it should not declare a fixed `meta_produces`.

Stream types are extensible identifiers. Extensions and local plugins may define their own representations without introducing new Fetchez stream classes or registries.

### Declaring hook dependencies

Use `meta_requires` when a hook depends on another registered hook to perform its intended operation.

```python
meta_requires = [
    {
        "hook": "global-product-index",
        "scope": "global",
        "stage": "collection",
    }
]
```

Here, the dependency must be configured as a global collection-stage hook.

Use `meta_related` for helpful companion components that are not required.

Dependency declarations are initially intended for discovery and documentation. They do not automatically insert missing hooks. Recipe schemas or modifiers may provide dependency validation or resolution separately.

### Stages and artifact types

`meta_stage` defines a hook's default execution stage, not a restriction on where it can run. For example, a filename filter may operate during manifest discovery, after archive extraction, or during collection processing.

Similarly, `meta_data_types` can advertise artifact compatibility:

```python
meta_data_types = ["raster"]
meta_effects = ["modifies-artifact"]
```

This does not mean the hook requires a `raster-stream`. Artifact types and stream types are separate concepts.

Hooks should continue handling unsupported inputs appropriately rather than relying exclusively on metadata declarations.

### Contributor recommendations

- Declare only capabilities that the hook actually implements.
- Keep effects broad and reusable rather than inventing a new effect for every operation.
- Use `meta_accepts` only when the hook requires a particular stream representation.
- Use `meta_requires` for genuine dependencies, not optional recommendations.
- Keep the hook's runtime behavior authoritative; metadata should describe it, not replace its own validation.
- Document any important stage limitations or assumptions in `meta_desc` and the hook's reference documentation.

Metadata declarations should improve discovery without restricting Fetchez's ability to support arbitrary entries, stream chunks, extensions, and local plugins.

## Testing Your Hook

```bash
# Check if it loaded
fetchez hooks list

# Run it
fetchez run srtm_plus --hook audit
```

## Developing & Sharing Presets
Presets (Macros) are the easiest way to share complex data engineering workflows without writing Python code. They allow you to bundle multiple processing steps into a single, shareable YAML snippet.

### The Preset Structure
Presets are standalone `.yaml` files placed in `~/.fetchez/presets/`. You can quickly see all active presets on your system by running `fetchez --list-presets`.

A preset requires a `name`, a `description`, and a list of `hooks` and their arguments.

`~/.fetchez/presets/clean_download.yaml`
```yaml
name: clean-download
description: "Unzip files and remove the original archive."
hooks:
  - name: unzip
    args:
      remove: true
```

### Module-Specific Overrides
Sometimes you build a macro that is only relevant to one specific dataset. For example, if you use the multibeam module, you might want a shortcut to only download the .inf metadata files.

You can restrict a preset so it only appears in the CLI menu for a specific module by adding the target_module key!

`~/.fetchez/presets/inf_only.yaml`

```yaml
name: inf_only
target_module: multibeam
description: 'multibeam Only: Fetch only inf files'
hooks:
  - name: filename_filter
    args:
      match: '.inf'
      stage: manifest
```
Now, `--inf-only` will show up when you run `fetchez multibeam --help`, but it won't clutter the global menu!

### Best Practices for Sharing
If you have developed a robust workflow (e.g., "Standard Archival Prep" or "Cloud Optimized GeoTIFF Conversion"), you can share it easily!

**Share the YAML:** You can post your .yaml file in a GitHub Issue or on our Zulip chat. Users can just drop it into their ~/.fetchez/hooks/presets/ folder.

**Bundle in a Python Package:** If you are building a Python package that extends `fetchez` (like `globato`), you can distribute presets automatically! Just place your YAML files in a package directory and register them in your pyproject.toml:

```toml
[project.entry-points."fetchez.hooks.presets"]
my_custom_presets = "my_package.hooks.presets"
```

**Contribute to Core:** If a preset is universally useful, you can propose adding it directly to the `fetchez/hooks/presets/` core directory via a Pull Request.

# 🔗 Sharing a Hook or Preset
Did you build a Hook or Preset that would be useful for the wider community? We'd love to incorporate it!

Submit a Pull Request adding your file to `fetchez/hooks/` or `fetchez/hooks/presets`.
