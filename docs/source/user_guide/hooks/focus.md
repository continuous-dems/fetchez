# Pipeline focus and entry stashes

Fetchez provides three related hooks for working with the active entries in a workflow:

- **`focus-sink`** replaces the active entries with file entries for named artifacts, discovered from active entries or the execution-wide artifact catalog.
- **`stash-entries`** saves a snapshot of the current entries under a named key.
- **`restore-entries`** replaces or extends the active entries using a previously saved snapshot.

These hooks are useful when a workflow generates intermediate products, needs subsequent hooks to process one particular output, or temporarily branches away from its original inputs. They operate on **pipeline entries**, not file contents: stashing and restoring do not copy, move, or delete files.

## Hook reference

| Hook | Default stage | Other supported stages | Purpose |
| --- | --- | --- | --- |
| `focus-sink` (`focus_sink`) | `collection` | No additional stages declared | Focus on named entry-level or catalog artifacts |
| `stash-entries` (`stash_entries`) | `collection` | `manifest`, `finalize` | Save the current entry list |
| `restore-entries` (`restore_entries`) | `collection` | `manifest`, `finalize` | Restore or merge a saved entry list |

`stash-entries` and `restore-entries` use execution-scoped storage in `FetchContext`. They do not require the original module to remain in the active entries. In a recipe, use **global hooks** when working with entries from multiple modules; module-local hooks see entries in their own scope.

## Save and restore entries

A stash is identified by a string key. The default key is `default` if none is specified.

```yaml
# Inside a recipe's global_hooks list:
global_hooks:
  - name: stash-entries
    args:
      key: original

  # Other collection-stage hooks may filter or replace entries here.

  - name: restore-entries
    args:
      key: original
```

The first hook stores the entries, passes them through unchanged, and the second returns the saved entries. A stash can be restored more than once. Saving the same key again replaces the earlier snapshot.

### Restore by replacement or merge

By default, `restore-entries` **replaces** the current list with the stored list:

```yaml
- name: restore-entries
  args:
    key: original
    merge: false
```

Set `merge: true` to append the stored entries *after* the currently active entries:

```yaml
- name: restore-entries
  args:
    key: original
    merge: true
```

Merging concatenates the lists; it does **not** deduplicate entries or resolve conflicting paths. A key that was never saved produces a warning and leaves the active entries unchanged. Saving an empty entry list is valid, and restoring it in replacement mode yields an empty list.

### Snapshot behavior

The stash saves a shallow copy of each entry dictionary while preserving its associated module object. It also makes new shallow copies when entries are retrieved. Therefore, later changes to top-level fields such as `dst_fn` do not change the saved values.

Nested dictionaries, lists, and live objects such as streams are **not deep-copied**. A stash is a lightweight structural snapshot, not a persistent checkpoint or a safe serialization of live processing state. Stashes exist only for one pipeline execution; they are not shared across separate recipe runs or regions.

## Focus on generated artifacts

`focus-sink` selects a named artifact and turns its path into an active file entry for subsequent hooks. It discovers matches from **both** the `artifacts` mappings of currently active entries and `self.context.artifacts`, the execution-scoped artifact catalog. Catalog entries remain discoverable even after an earlier hook has filtered out or replaced their originating pipeline entries.

### Register and focus an entry-level artifact

Existing hooks can continue to register artifacts directly on an entry:

```python
entry.setdefault("artifacts", {})["processed_raster"] = "/data/processed.tif"
```

A subsequent collection-stage hook can focus on that output:

```yaml
- name: focus-sink
  args:
    target: processed_raster
```

The original module association and `artifacts` mapping are retained for these legacy entry-level artifacts. A single artifact key may contain one path or a list of paths.

### Register and focus a collection-level artifact

A custom hook that generates a product from several source modules can publish that output to the shared catalog, without claiming that an individual input module produced it:

```python
# After the output file has been successfully produced:
self.context.artifacts.publish(
    "final-dem",
    "/outputs/coastal_dem.tif",
)
```

A later global collection hook can then focus on it:

```yaml
- name: focus-sink
  args:
    target: final-dem
```

The artifact remains available even if there are **no active source entries** at that point. No `scratch` module needs to be added explicitly to the recipe: `run_fetchez()` creates a designated runtime Scratch instance for this purpose.

### How focused entries are represented

For each distinct selected path, `focus-sink` constructs an entry with:

- `dst_fn` set to the artifact path, `url` set to `file://` plus that path, and `status: 0`.
- `data_type` derived from the selected key, such as `final-dem_artifact`.
- An `artifacts` mapping: preserved from the originating active entry for entry-level artifacts, or `{target: path}` for catalog-only artifacts.
- For catalog-derived entries, `artifact_name` and `artifact_owner` fields recording the catalog metadata (`artifact_owner` can be `None`).

Duplicate paths are emitted once. The hook processes active entry artifacts first, followed by catalog records; the first occurrence establishes the resulting entry and runtime owner. If `target` is omitted, or no matching usable artifact is found, it warns and passes the original entries through unchanged.

### Artifact producer versus runtime owner

The artifact catalog's `owner` field describes an **identified producer**; a missing owner (`None`) is meaningful and is not silently replaced with `"scratch"`. Fetchez still requires an owning module object for each active `(module, entry)` pair, however. When a catalog artifact becomes a focused entry, `focus-sink` resolves that *runtime entry owner* as follows:

| Artifact source / producer | Runtime owner of focused entry |
| --- | --- |
| Artifact attached to an active entry | That entry's module |
| Catalog record with a recognized module owner ID | The corresponding source module (from active entries or the compiled plan) |
| Catalog record with `owner=None` | Execution's designated `Scratch` instance |
| Catalog record with an unknown module owner ID | Execution's `Scratch` instance, with a warning |

`Scratch` is a valid owner during subsequent grouped-stage processing, but is **not** included in ordinary module discovery or acquisition. Its job here is to carry an already-generated entry through the pipeline, **not** to assert that it created the underlying artifact. The original catalog record remains unchanged.

Known producer IDs can be resolved from active entries or a compiled plan's module lookup. For direct Python executions without that mapping, a catalog artifact whose source entries have disappeared may use Scratch as its runtime owner even if it declares a producer ID. If no designated Scratch exists (for example, when calling the hook manually without a fully initialized execution), an unresolved catalog artifact is skipped with a warning.

## Example: focus, then restore the original inputs

The following illustrates an ordering pattern for collection-stage hooks. `processed_raster` must already have been registered by an upstream hook, either in an entry's `artifacts` mapping or in the execution catalog; this snippet does not generate the raster itself.

```yaml
global_hooks:
  - name: stash-entries
    args:
      key: source_entries

  - name: focus-sink
    args:
      target: processed_raster

  # Subsequent collection hooks here operate on processed_raster entries.

  - name: restore-entries
    args:
      key: source_entries
      merge: false
```

With `merge: false`, the workflow continues using only the original entries after restoration. With `merge: true`, it continues using both the focused artifact entries and the saved originals, potentially including duplicates.

Hook ordering matters: the stash must execute before the focus operation, and the restore must execute after it. Keep hooks in the same stage when you need predictable sequential behavior; Fetchez groups execution by stage, not solely by their position in the recipe.

## Python hook usage

In custom hooks, the shared execution context exposes named stashes and the artifact catalog directly:

```python
self.context.stashes.save("before_processing", entries)

# Later, from another hook in the same execution:
if self.context.stashes.has("before_processing"):
    entries = self.context.stashes.get("before_processing")
```

For generated outputs, publish only after successful completion; `focus-sink` can retrieve the registered path even if the producing entry has since left the active pipeline:

```python
self.context.artifacts.publish(
    "qc-report", "/outputs/quality_report.json", metadata={"kind": "qc"}
)

reports = self.context.artifacts.find("qc-report")
# Each result is an Artifact record with .name, .path, .owner, .metadata.
```

The catalog also provides `get(name, owner=...)` for an unambiguous single result; it raises `KeyError` if none match and `ValueError` if several match. Artifacts are execution-scoped, not a durable cross-run index. Publication does not verify that a file exists, so producer hooks should register outputs only after they have been successfully created.

The context storage API also supports `keys()` to inspect saved names. Direct calls to `get()` with an unknown key raise `KeyError`; the `restore-entries` hook instead warns and passes entries through unchanged.

At present, these hooks receive and return lists of `(module, entry)` pairs under Fetchez's existing collection-hook interface. The module association is preserved when entries are stashed and restored. The Python context example assumes execution has bound `self.context` to the hook; manually instantiated hooks require equivalent context setup.

## Configuration summary

| Hook | Argument | Default | Behavior |
| --- | --- | --- | --- |
| `focus-sink` | `target` | `None` | Artifact name to select from active entries and `context.artifacts` |
| `stash-entries` | `key` | `default` | Name under which to save the current entries |
| `restore-entries` | `key` | `default` | Name of the saved entries to retrieve |
| `restore-entries` | `merge` | `false` | Append saved entries to current entries instead of replacing them |
| `stash-entries`, `restore-entries` | `stage` | `collection` | May also be set to `manifest` or `finalize` |

For registered metadata and available arguments, use:

```bash
fetchez hooks info focus-sink
fetchez hooks info stash-entries
fetchez hooks info restore-entries
```

See [Hooks and Presets](../hooks_and_presets.md) for pipeline stages and configuration, [Set Entry](set_entry.md) for assigning entry fields, and [Filename Filter](filename_filter.md) for selecting entries by filename.
