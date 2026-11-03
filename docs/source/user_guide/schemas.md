# ✅ Recipe Schemas

Schemas validate a prepared recipe configuration. They check that a workflow meets your requirements **before** any data is fetched, turning silent mistakes into clear, early errors.

> **Running example:** Our [San Diego DEM recipe](recipes.md) targets an arbitrary bounding box. If your team delivers data on quarter-degree tiles, you want the recipe to refuse anything that doesn't snap to that grid — caught at compile time, not after a partial download.

## What Is a Recipe Schema?

A schema is a reusable validator. It receives a prepared recipe configuration and returns whether that configuration is valid, along with any errors it found.

```text
YAML recipe  →  expansion  →  modifiers  →  placeholders  →  schemas  →  execution
                                                                 ↑
                                                       your validation rules
```

A schema answers a question about the recipe as a whole: *does this workflow satisfy the constraints we care about?* It does not fetch data, process files, or change the pipeline.

## When to Use a Schema

Schemas are most valuable when a recipe is shared, reused, or run unattended:

| Situation                             | What a schema catches                                                            |
|---------------------------------------|----------------------------------------------------------------------------------|
| **Enforcing workflow requirements**   | A recipe that omits a mandatory audit hook, or targets an unexpected region      |
| **Standardising production recipes**  | Team-wide conventions: naming, output locations, required metadata               |
| **Validating deliverables**           | Output tiling schemes, coordinate reference systems, or coverage extents         |
| **Enforcing delivery specifications** | Configured tiling schemes, target CRS, region boundaries, and output conventions |
| **Catching configuration mistakes**   | Mismatched regions, contradictory arguments, missing required fields             |

The common thread is that these are **requirements you already know**, expressed once and checked automatically on every run. A schema is cheaper than discovering the problem halfway through a fetch.

Recipe schemas validate intended workflow configuration. To verify generated files or data quality, use processing or validation hooks that inspect the actual outputs.

## Using Schemas in YAML

Declare schemas in a top-level `schemas` block. Each entry is identified by `name`:

```yaml
project:
  name: "My_Strict_Project"

schemas:
  - name: "quarter-degree-tile"

region: [-120.0, -119.75, 33.0, 33.25]  # Your exact delivery tile
```

Here the `quarter-degree-tile` schema checks that the region snaps to a quarter-degree tile in WGS84. If it doesn't, compilation fails with an explanation.

Schemas are currently configured **by name only**. Unlike modifiers, they are not passed an `args` mapping, so any per-run configuration must live inside the schema itself or be inferred from the recipe.

### Applying a Schema from the CLI

Schemas can also be supplied at invocation time:

```bash
fetchez run -R -120/-119.75/33/33.25 --schema quarter-degree-tile my_strict_project.yaml
```

## Validation Versus Processing

This distinction is worth stating plainly, because the two mechanisms look similar in YAML:

| | Modifier | Schema |
|---|----------|--------|
| **Purpose** | Change the configuration | Judge the configuration |
| **Effect on pipeline** | Rewrites modules, hooks, arguments | None — the pipeline is unchanged |
| **On failure** | Raises if it can't do its job | Raises if the recipe violates a rule |
| **Typical use** | Adapt a recipe to a situation | Enforce a requirement |

A schema observes; it does not modify. Schemas are intended to be read-only validators. A correctly implemented schema examines the configuration and reports violations without modifying the workflow. If you need to *change* the workflow, use a [modifier](modifiers.md) instead.

## Schema Execution and Failure Handling

Schemas run late in compilation — after bundles and presets have expanded, after modifiers have applied their changes, and after `%placeholder%` values have been injected. This means a schema validates the configuration that will actually execute, not the raw YAML you wrote.

When a schema reports a violation, compilation raises a `ValueError` listing the errors it found. Because this happens during compilation, **no data is fetched** — the recipe fails cleanly and early.

Schema violations normally stop compilation with a ValueError containing the collected validation errors. With ignore_failures=True, reported schema violations are logged as warnings and compilation continues.

Exceptions that prevent compilation from completing—such as an unavailable schema or invalid component configuration—are different from reported schema violations. During multi-region execution, such failures may cause the affected batch to be skipped when permissive failure handling is enabled.

## Inspecting and Validating Recipes

Compile a recipe to see the prepared configuration that schemas will evaluate:

```bash
fetchez recipes compile my_recipe.yaml
```

To validate without producing compiled output:

```bash
fetchez recipes validate my_recipe.yaml
```

Both are useful in CI, where you want a recipe checked on every commit without triggering a fetch.

## Using Multiple Schemas

Declare as many schemas as your workflow requires:

```yaml
schemas:
  - name: "quarter-degree-tile"
  - name: "requires-audit-hook"
  - name: "wgs84-region"
```

All declared schemas run. Errors accumulate across the full set rather than stopping at the first failure, so a single compile tells you **everything** that's wrong — not just the first problem. Fix them all at once rather than iterating one error at a time.

Schemas are independent of one another; none can suppress or short-circuit another.

## Creating Custom Schemas

Schemas are registered components, so you can write your own and register them locally or ship them in an extension:

* **[Plugins & Extensions](/user_guide/plugins_and_extensions.md)** — Register a local schema or package one for distribution
* **[Contributor Guide](/contribute/index.md)** — Implement and test custom schemas

---

**Related:** [Recipe Modifiers](modifiers.md) transform the configuration that schemas validate. [Recipes](recipes.md) covers the overall recipe structure.
