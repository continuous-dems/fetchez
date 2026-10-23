# 🏛️ Fetchez Architecture and Design Philosophy

Fetchez is a modular, extensible geospatial ETL framework. Its purpose is to provide reusable acquisition, representation, processing, and workflow capabilities that can be composed through Python, the CLI, YAML recipes, and third-party extensions.

This document describes the architectural direction contributors should preserve. It is design guidance, not a claim that every planned capability has already been implemented. Refer to the current API and component documentation for supported behavior.

## Guiding principle

**One framework execution model, many ways to compose it.** A new provider, hook, or extension should cooperate with the existing Fetchez lifecycle rather than construct a competing execution pathway.

Fetchez supplies generic capabilities and execution semantics; domain packages supply interpretations, policies, and compositions. Generic does not mean geospatially unaware: CRS handling, data acquisition, artifact types, readers, and streams can be generic geospatial capabilities. DEM-specific fusion policies and vertical-datum decisions belong in the appropriate domain extension.

## Conceptual layers

```text
CLI / Python API / YAML / external applications
                    |
         Recipe and workflow resolution
                    |
       Component registries and metadata
                    |
            Fetchez core runtime
                    |
     Entries / artifacts / optional streams
                    |
           Hooks and domain extensions
```

These layers describe responsibilities, not mandatory steps for every workflow. A simple acquisition task need not initialize a stream.

## Component responsibilities

| Component | Responsibility |
| --- | --- |
| Module | Discover source resources and describe them as Fetchez entries. |
| Entry | Extensible mapping carrying source, artifact, and processing metadata. |
| Hook | Perform an operation within the framework's defined processing lifecycle. |
| Data type | Describe the generic representation of an artifact, where supported. |
| Detector | Infer a generic artifact representation, where available. |
| Reader | Decode data into a supported stream representation. |
| Profile | Configure how a reader interprets and exposes input. |
| Stream | Carry a defined representation through processing hooks. |
| Bundle | Reusable composition of modules. |
| Preset | Reusable composition of hooks. |
| Recipe | Describe and orchestrate a complete workflow. |
| Modifier / schema | Transform or validate recipe configuration where supported. |
| Extension | Package registered capabilities and domain-specific workflows without replacing the core runtime. |

The presence and exact public interfaces of newer component categories may vary by release. Check the registries before assuming a proposed category exists.

## Boundaries that matter

### Discovery versus acquisition versus processing

Modules normally discover and register resources; the framework's acquisition machinery should manage downloading, retries, and caching when applicable. Processing after discovery belongs in hooks, readers, or other existing components. Provider-specific API pagination and search semantics belong with the provider module; raster conversion and archive extraction should not be hardcoded into each provider.

### Representation versus domain meaning

A raster reader should describe raster data, not assume it contains elevation. A vector reader should not assume every feature is a coastline. Domain-specific packages such as Globato may adapt generic streams to elevation records and apply DEM-specific weighting, uncertainty, or fusion semantics.

### Declarative configuration versus execution

Bundles, presets, and recipes are ways to express or reuse workflows, not alternative execution engines. Python and YAML interfaces should converge on the same component semantics and runtime behavior. Do not implement a second pipeline runner solely for a convenience API or provider integration.

### Open extension contracts

Entries may carry extension-specific keys. Preserve documented core fields and their meanings; do not silently repurpose `data_type`, `dst_fn`, `stream_type`, or other shared fields. Artifact types and stream representations are distinct concepts.

### Compatibility and metadata

Component metadata supports discovery, documentation, and compatibility checks where implemented. For hooks, `meta_stage`, `meta_effects`, `meta_accepts`, `meta_produces`, `meta_requires`, `meta_data_types`, and `meta_related` have established descriptive roles. Do not assume that metadata automatically inserts missing hooks or enforces every declared constraint.

## Design values

1. **Composition over special-case pathways.** Prefer combining small registered capabilities to creating a monolithic provider workflow.
2. **Shared primitives over duplicated infrastructure.** Improve reusable fetching, entry handling, output management, or stream processing once rather than repeating it in providers.
3. **Explicit contracts over implicit coupling.** Document inputs, outputs, side effects, ordering assumptions, and dependencies.
4. **Optional capabilities over mandatory complexity.** Simple download workflows should remain simple; heavy geospatial dependencies should be optional when possible.
5. **Incremental compatibility.** Prefer focused changes, regression tests, and migration paths over speculative redesigns.
6. **Discoverability and reproducibility.** Components should remain usable through registries and documented CLI/API/recipe surfaces as appropriate.
7. **Domain-neutral core, domain-rich extensions.** Keep domain-specific policy where it belongs without weakening generic framework utilities.

## Before changing framework internals

Explain why an existing module, hook, reader, profile, preset, bundle, recipe, or extension cannot solve the problem. Identify the smallest reusable contract that needs improvement. Changes to registry, recipe, core runtime, or public API should preserve existing execution paths and include regression tests across the affected interfaces.
