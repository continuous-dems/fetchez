# Pipeline focus and entry stashes

Fetchez provides three related hooks for working with the active entries in a workflow:

- **`focus-sink`** replaces the active entries with file entries for artifacts produced by an earlier hook.
- **`stash-entries`** saves a snapshot of the current entries under a named key.
- **`restore-entries`** replaces or extends the active entries using a previously saved snapshot.

These hooks are useful when a workflow generates intermediate products, needs subsequent hooks to process one particular output, or temporarily branches away from its original inputs. They operate on **pipeline entries**, not file contents: stashing and restoring do not copy, move, or delete files.

## Hook reference

| Hook | Default stage | Other supported stages | Purpose |
| --- | --- | --- | --- |
| `focus-sink` (`focus_sink`) | `collection` | No additional stages declared | Focus on artifacts registered in the current entries |
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

`focus-sink` selects a named artifact from the `artifacts` mappings attached to the **currently active** entries. It is typically used after an earlier hook produces one or more outputs without making those outputs the primary entries.

For example, an earlier hook may register:

```python
entry.setdefault("artifacts", {})["processed_raster"] = "/data/processed.tif"
```

A subsequent collection hook can select it:

```yaml
- name: focus-sink
  args:
    target: processed_raster
```

The focused entry has `dst_fn` set to the artifact path, a `file://` URL, `status: 0`, and a `data_type` derived from the target name (for example, `processed_raster_artifact`). Its `artifacts` mapping is retained. Any subsequent hook in the same stage sees the focused entries rather than the original ones.

One target may contain a single path or a list of paths. Duplicate paths are emitted only once, retaining the first matching module association. If no active entry exposes the target, the hook logs a warning and returns the original entries. If `target` is omitted, it also passes entries through unchanged.

**Current limitation:** `focus-sink` reads `entry["artifacts"]`; it does not yet look up artifacts in an execution-wide catalog. If a prior hook has removed the entry holding an artifact, `focus-sink` cannot discover that artifact from the active entries alone. The planned artifact catalog will address this separately.

## Example: focus, then restore the original inputs

The following illustrates an ordering pattern for collection-stage hooks. `processed_raster` must already have been registered in `entry["artifacts"]` by an upstream hook; this snippet does not generate the raster itself.

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

In custom hooks, the shared execution context exposes named stashes directly:

```python
self.context.stashes.save("before_processing", entries)

# Later, from another hook in the same execution:
if self.context.stashes.has("before_processing"):
    entries = self.context.stashes.get("before_processing")
```

The context storage API also supports `keys()` to inspect saved names. Direct calls to `get()` with an unknown key raise `KeyError`; the `restore-entries` hook instead warns and passes entries through unchanged.

At present, these hooks receive and return lists of `(module, entry)` pairs under Fetchez's existing collection-hook interface. The module association is preserved when entries are stashed and restored. The Python context example assumes execution has bound `self.context` to the hook; manually instantiated hooks require equivalent context setup.

## Configuration summary

| Hook | Argument | Default | Behavior |
| --- | --- | --- | --- |
| `focus-sink` | `target` | `None` | Artifact key to select from active `entry["artifacts"]` mappings |
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
