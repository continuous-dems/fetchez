# 🏷️ Identity in Fetchez

Fetchez uses several identifiers for different purposes. A workflow occurrence, a provider configuration, and a data source are not interchangeable identities. Keeping them separate allows a recipe to reuse the same source for different processing paths without changing the source's provenance or acquisition cache.

Fetchez also provides a shared `make_id()` utility for generating deterministic, namespaced identities. This utility defines how an identifier is generated from explicit inputs, while the framework's existing identity helpers define what those inputs mean for modules, sources, datasets, and processed contributions.

| Identifier                         | Applies to                                   | Purpose                                                                            | Defined or accessed through                                        |
|------------------------------------|----------------------------------------------|------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| Recipe `id` / `module.instance_id` | One module occurrence in a compiled workflow | Human-readable reference for other components                                      | `modules[].id`, `module.instance_id`, `context.plan.modules_by_id` |
| `module.module_id()`               | Provider invocation/configuration            | Deterministic identity used for the module's discovery cache                       | `FetchModule.module_id()`                                          |
| `source_id(entry)`                 | A physical or logical input source           | Identify the originating source represented by an entry                            | `fetchez.entry.source_id`                                          |
| `dataset_id(entry)`                | Dataset/entry identity                       | Identify a dataset from its entry information, independently of the workflow label | `fetchez.entry.dataset_id`                                         |
| `contribution_id`                  | Processed-entry identity information         | Record distinctions relevant to a processed contribution                           | Entry metadata and relevant provenance helpers                     |

The last three identifiers depend on the entry and its metadata. They are **not** aliases for a recipe ID. A workflow label must not be inserted automatically into `contribution_id` or used to manufacture independent source or survey evidence.

`dataset_id(entry)` identifies the current dataset state represented by an entry. It begins with the underlying source or dataset identity and incorporates semantic processing distinctions recorded through `set_contribution_id()`. Hooks that materially change the represented data should update the contribution metadata so that separately processed versions of the same source receive distinct dataset IDs.

`source_id(entry)` remains associated with the originating source, while `dataset_id(entry)` may evolve as processing occurs. Workflow occurrence IDs do not affect either identity.

## Generate deterministic IDs with `make_id()`

Fetchez provides a general-purpose identity utility for generating stable, namespaced identifiers from explicit values:

```python
from fetchez.utils.identity import make_id

artifact_id = make_id(
    "globato:side_stack",
    source="survey_001",
    resolution=3,
    version=1,
)
```

`make_id()` uses canonical JSON serialization and SHA-256 hashing to produce identifiers that are deterministic across processes and runs, provided the same inputs and identity contract are used.

Unlike `source_id()` and `dataset_id()`, **`make_id()` does not interpret Fetchez entries or determine what constitutes a dataset or source**. It simply generates an identity from the values supplied by the caller.

### Identity namespaces

Every generated identifier requires a namespace describing its purpose:

```python
cache_id = make_id("fetchez:cache", source_url)
artifact_id = make_id("globato:artifact", source_id, operation)
```

The returned identifier has the form:

```text
<namespace>:<sha256-prefix>
```

By default, the digest portion contains 16 hexadecimal characters (64 bits). The `length` argument can select between 1 and 64 characters:

```python
make_id("example:artifact", source_id, length=32)
```

Namespaces help distinguish identities created for different purposes, even when their input values happen to be identical.

For persisted identities, consider including an explicit identity-schema version in the namespace:

```python
make_id(
    "globato:side_stack:v1",
    source=source_id,
    resolution=resolution,
)
```

This allows identity definitions to evolve without silently changing the meaning of previously stored identifiers.

### Canonicalization

Identity inputs are converted into a deterministic JSON-compatible representation before hashing.

Supported values include:

- Strings, booleans, integers, finite floats, and `None`.
- `pathlib.Path` objects, represented as strings.
- Mappings with string keys, sorted deterministically.
- Lists and tuples, preserving element order.
- Sets and frozensets, sorted by their canonical JSON representations.

For example, mapping insertion order does not affect the resulting identity:

```python
a = make_id("example", {"source": "survey_001", "version": 2})
b = make_id("example", {"version": 2, "source": "survey_001"})

assert a == b
```

Ordered collections are different:

```python
a = make_id("example", ["a", "b"])
b = make_id("example", ["b", "a"])

assert a != b
```

Unsupported Python objects and non-finite floating-point values are rejected rather than converted through `repr()` or object type names. Callers must provide explicit, deterministic representations for custom values.

The underlying helpers are also available when needed:

```python
from fetchez.utils.identity import canonicalize, canonical_json
```

### Choosing identity inputs

`make_id()` guarantees deterministic hashing, but **the caller remains responsible for selecting the correct semantic inputs**.

For example, a derived artifact identity might include the originating dataset, processing operation, and settings that materially affect the output:

```python
artifact_id = make_id(
    "globato:raster:v1",
    source=source_id,
    operation="warp",
    resolution=3,
    target_crs="EPSG:4326",
)
```

Avoid incorporating transient values such as timestamps, temporary paths, process IDs, or unrelated runtime metadata unless they intentionally distinguish the result.

In particular:

- Use `source_id(entry)` to identify the originating source.
- Use `dataset_id(entry)` to identify the dataset state represented by an entry.
- Use `set_contribution_id()` when processing changes the entry's represented dataset.
- Use recipe `id` / `module.instance_id` to identify a workflow occurrence.
- Use `make_id()` when a new deterministic identity is needed for an artifact, cache entry, operation, or other purpose not covered by those existing identities.

An identity generated with `make_id()` is not automatically a dataset ID, content checksum, or provenance record.

### Stability and compatibility

The canonicalization rules, namespace, selected input fields, and hashing algorithm collectively define an identity contract.

Changing any of these may change generated identifiers and invalidate previously persisted cache keys or artifact references.

For identities intended to persist across releases, document their namespace and input fields, and version the identity definition when making incompatible changes.

The default 16-character digest prefix provides a practical compact identifier, but it is not a uniqueness guarantee. Applications requiring stronger collision resistance can request a longer digest.

`make_id()` does not read file contents, inspect runtime objects, modify entries, or perform filesystem operations.

## Name a module occurrence

```yaml
modules:
  - id: reference_surface
    module: tnm
    args: {datasets: "1"}

  - id: comparison_surface
    module: tnm
    args: {datasets: "1"}
```

These are two distinct workflow occurrences. They can have the same `module_id()` because their acquisition configurations match. Their `instance_id` values are different because the recipe gives them different names. They can also run different hooks or be referenced separately by a downstream hook.

The `id` field is **recipe metadata**: place it beside `module`, not inside `args`. It does not rename a registered provider or become a provider constructor argument.

## Find modules from a hook

A compiled recipe produces a `PipelinePlan` containing the module objects. During execution, modules and hooks receive a shared context, which provides access to that plan:

```python
class CompareHook(FetchHook):
    # ... hook metadata and setup ...

    def run(self, entries):
        plan = self.context.plan if self.context else None
        if plan is not None:
            reference = plan.modules_by_id["reference_surface"]
            # Inspect reference.results or other module state as appropriate.
        return entries
```

`context.plan` is optional: direct calls to `run_fetchez()` without a compiled recipe have an execution context but may have no plan. Hook implementations intended to work both ways should handle `None`.

Each `(module, entry)` pair already conveys the owning occurrence. When processing entries, prefer `module.instance_id` to adding the recipe label to an entry's scientific metadata.

## Automatic and preconfigured IDs

Module definitions without an explicit ID receive positional display labels such as `entry_1`. These are conveniences, **not stable names**: adding, removing, or reordering modules may change them. Use explicit IDs for references between components.

Python callers can also preconfigure a `FetchModule` instance with `module.instance_id`. When a recipe explicitly supplies an `id` for that instance, the recipe's explicit label takes precedence. Generated labels avoid reserved user-supplied labels. Two user-defined labels that resolve to the same ID are invalid within one compiled plan.

A single Python module object cannot represent two separate occurrences in the same compiled plan; use separate instances or class declarations.

## Cache identity and provenance

`module_id()` is based on the module's canonical configuration. Changing only its workflow `instance_id` should not change the module discovery cache identity. The same provider can therefore be referenced under two names while retaining the same source and dataset semantics.

This is also why two named occurrences must not automatically be treated as independent observations in validation or scoring. Workflow roles and physical evidence are separate concepts.

## Discovery and execution context

`Recipe.compile()` prepares the plan without running module discovery. `PipelinePlan.execute()` calls the core engine, where discovery (`module.run()`) occurs before manifest hooks. Direct Python callers may pass `discover=False` to `run_fetchez()` for modules whose results are already populated. A shared execution context also provides cooperative cancellation via `context.cancel()` and `context.cancelled`; module and hook context references are cleared after the run.

For the recipe API and examples, see [Recipes](recipes.md). For bundle inheritance behavior, see [Modules and Bundles](modules_and_bundles.md).
