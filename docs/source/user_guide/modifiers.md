# 🔧 Recipe Modifiers

Modifiers transform a recipe configuration **before** Fetchez executes it. They let one recipe serve several purposes without duplicating YAML files.

> **Running example:** Our [San Diego DEM recipe](recipes.md) is useful as written. But suppose you want the same recipe to optionally skip a slow source, or to add reporting only in production. Rather than maintaining three near-identical YAML files, you add a modifier.

## What Is a Recipe Modifier?

A modifier is a component that receives a prepared recipe configuration, changes it, and returns the result. Fetchez then executes the modified configuration as if you had written it that way by hand.

Conceptually:

```text
YAML recipe  →  bundle/preset expansion  →  modifiers  →  execution
                                              ↑
                                     your transformations
```

Because modifiers operate on the configuration rather than on data, they can change *which* modules run, *what* arguments they receive, and *which* hooks are attached — all at runtime.

This is different from a [hook](hooks_and_presets.md), which processes data flowing through a pipeline. A modifier shapes the pipeline itself; a hook works inside it.

## When to Use a Modifier

Modifiers are the right tool when the variation you need is **structural** rather than data-related:

| Situation | Why a modifier fits |
|-----------|---------------------|
| **Conditional processing** | Skip an expensive source for a quick test run, or disable a validation step in development |
| **Workflow specialisation** | Turn one general-purpose recipe into a domain-specific variant (coastal vs. offshore, production vs. staging) |
| **Selecting data sources** | Remove or substitute modules from a shared bundle without editing the bundle |
| **Adding optional reporting** | Attach an audit or notification hook only when running in CI or on a schedule |
| **Adapting reusable recipes** | Take a recipe published by someone else and bend it to your environment without forking it |

If you find yourself copying a recipe to change two lines, a modifier is probably the better answer.

## Using Modifiers in YAML

Add a `modifiers` block at the top level of your recipe. Each entry has a `name` and an optional `args` mapping:

```yaml
---
project:
  name: "My_Project"

modifiers:
  - name: exclude_module
    args:
      modules: margrav/charts

region: [-120.0, -119.75, 33.0, 33.25]

modules:
  - bundle: my-bathymetry-bundle
```

Here the `exclude_module` modifier removes `margrav` and `charts` from the expanded bundle before the recipe runs.

### Passing Arguments

Arguments are supplied as a mapping under `args`, and are passed to the modifier's constructor:

```yaml
modifiers:
  - name: exclude_module
    args:
      modules: margrav/charts
  - name: set_threads
    args:
      threads: 8
```

Some modifiers take no arguments, in which case `args` can be omitted entirely:

```yaml
modifiers:
  - name: production_defaults
```

Argument names must match the modifier's constructor. If a modifier does not accept arbitrary keyword arguments, supplying an unrecognised name raises a `TypeError` rather than being silently ignored — so a typo surfaces immediately.

Path-like arguments are resolved for you. Keys such as `file`, `path`, `outdir`, and `cache_dir` are resolved relative to the recipe's directory, while `output` and `output_grid` are resolved relative to the batch's output directory. Remote URLs (`http://`, `s3://`, and similar) are left untouched.

### Applying a Modifier from the CLI

Modifiers can also be supplied at invocation time, which is handy for one-off variations:

```bash
fetchez run my_project.yaml --modifier exclude_module:modules=margrav/charts
```

## Combining Modifiers

Modifiers run **in the order they are declared**, and each one receives the output of the previous. Later modifiers therefore see the changes made by earlier ones.

```yaml
modifiers:
  - name: exclude_module
    args:
      modules: margrav/charts
  - name: add_reporting
```

In this recipe, `add_reporting` sees a configuration that `margrav` and `charts` have already been removed from. If `add_reporting` inspected the module list, it would not find them.

This ordering property is what makes composition useful — but it also means order matters. If a modifier depends on a module that another modifier removes, declare the dependent one first.

## Inspecting the Result

Because modifiers change the configuration before execution, it's worth checking what they produced. Compile the recipe without running it:

```bash
fetchez recipes compile my_project.yaml
```

To see the prepared configuration in a specific format:

```bash
fetchez recipes compile my_project.yaml --format yaml
fetchez recipes compile my_project.yaml --format json
```

The compiled output reflects all expansions and modifications, so it's the authoritative view of what will actually run. This is also the fastest way to debug a modifier that isn't behaving as expected.

## Discovering Available Modifiers

List the modifiers registered in your environment, including those from installed extensions:

```bash
fetchez recipes modifiers list
```

Inspect a specific modifier for its arguments and behaviour:

```bash
fetchez recipes modifiers info exclude_module
```

## Important Behaviour

Modifiers sit at a specific point in the compilation sequence, and knowing where matters.

### Expansion Order

During compilation, Fetchez performs these steps in order:

1. **Bundles and presets are expanded** into concrete modules and hooks
2. **Modifiers are applied**, in configured order
3. **Execution options** are applied (shared cache, refresh behaviour)
4. **`%placeholder%` values are injected**
5. **Schemas validate** the resulting configuration
6. **Components are instantiated**

Three consequences follow:

* **Modifiers see expanded modules, not bundle references.** By the time a modifier runs, `- bundle: my-bathymetry-bundle` has become a list of individual modules. Target the expanded members, not the bundle name.
* **Modifiers see unresolved placeholders.** A modifier runs before `%name%`, `%batch_name%`, and friends are substituted, so it observes the literal placeholder strings. Matching on a resolved value won't work.
* **Modifiers run before validation.** Anything a modifier changes is subject to schema validation, so a modifier can fix or break a recipe's compliance.

### Configuration Mutation

A modifier's `apply()` method receives the configuration and **must return it**. Returning `None` will break compilation.

Fetchez copies the configuration's containers before handing it over, so a modifier can freely add, remove, or rewrite keys without affecting the original recipe object. Live Python component instances, however, are passed through by identity rather than cloned — see [Recipes](recipes.md) for how runtime components behave.

Modifiers may also change the recipe's `region`. Because the effective region is resolved *after* modifiers run, a modifier that rewrites `region` genuinely changes the area processed. Note that a compiled pipeline must still resolve to exactly one region.

### Per-Batch Application

Modifiers are applied once per batch. When a recipe targets multiple regions, each batch is compiled separately, and each compilation runs the modifier chain against that batch's own configuration — including that batch's region. A modifier therefore sees a single batch's context, not the whole multi-region run.

### Failure Handling

An unknown modifier name raises a `ValueError` and stops compilation. If you pass `ignore_failures=True` (or the equivalent CLI flag), Fetchez logs a warning and skips the missing modifier instead, allowing the rest of the recipe to proceed.

## Creating Your Own

Modifiers are registered components. You can write your own and register them locally or ship them as part of an extension:

* **[Plugins & Extensions](/user_guide/plugins_and_extensions.md)** — Register a local modifier or package one for distribution
* **[Contributor Guide](/contribute/index.md)** — Implement and test custom modifiers

---

**Related:** [Recipe Schemas](schemas.md) validate the configuration that modifiers produce. [Recipes](recipes.md) covers the overall recipe structure.
