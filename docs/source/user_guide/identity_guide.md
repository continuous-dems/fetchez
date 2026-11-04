# 🏷️ Identity in Fetchez

Fetchez uses several identifiers for different purposes. A workflow occurrence, a provider configuration, and a data source are not interchangeable identities. Keeping them separate allows a recipe to reuse the same source for different processing paths without changing the source's provenance or acquisition cache.

| Identifier                         | Applies to                                   | Purpose                                                                            | Defined or accessed through                                        |
|------------------------------------|----------------------------------------------|------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| Recipe `id` / `module.instance_id` | One module occurrence in a compiled workflow | Human-readable reference for other components                                      | `modules[].id`, `module.instance_id`, `context.plan.modules_by_id` |
| `module.module_id()`               | Provider invocation/configuration            | Deterministic identity used for the module's discovery cache                       | `FetchModule.module_id()`                                          |
| `source_id(entry)`                 | A physical or logical input source           | Identify the originating source represented by an entry                            | `fetchez.entry.source_id`                                          |
| `dataset_id(entry)`                | Dataset/entry identity                       | Identify a dataset from its entry information, independently of the workflow label | `fetchez.entry.dataset_id`                                         |
| `contribution_id`                  | Processed-entry identity information         | Record distinctions relevant to a processed contribution                           | Entry metadata and relevant provenance helpers                     |

The last three identifiers depend on the entry and its metadata. They are **not** aliases for a recipe ID. A workflow label must not be inserted automatically into `contribution_id` or used to manufacture independent source or survey evidence.

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
