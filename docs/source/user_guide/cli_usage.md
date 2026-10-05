# 💻 Command Line Interface

The `fetchez` command line tool allows you to chain modules and hooks together.

Build and optionally execute an ad-hoc Fetchez pipeline.

The `build` command composes registered Modules, Bundles, Hooks, and Presets
into a Fetchez recipe. Components are chained from left to right and may be
executed immediately or exported as reusable YAML.

## Pipeline Composition:

Source components are Modules or Bundles.

Processing components are Hooks or Presets. Their scope is determined by
their position in the command chain:

* Hooks and Presets before the first source are global.
* Hooks and Presets after a Module or Bundle apply to that source.
* Processing components continue to apply to the most recent source until another Module or Bundle is encountered.

Module and Hook arguments follow the component they configure.

## Examples:

Apply a global hook before fetching a source:

```bash
fetchez build audit tnm
```

audit -> global hook
tnm   -> module

Attach processing to a single source:

```bash
fetchez build tnm raster_warp --res 1s
```

tnm         -> module
raster_warp -> hook attached to tnm

Compose multiple independently processed sources:

```bash
fetchez build audit tnm raster_warp --res 1s copernicus checksum
```

audit       -> global hook
tnm         -> first module
raster_warp -> hook attached to tnm
copernicus  -> second module
checksum    -> hook attached to copernicus

Select members of a registered bundle:

```bash
fetchez build -R <W/E/S/N> glob-tnm --select products=1m/1_9as
```

Hooks may also be supplied using `--hook` and `--global-hook` for concise or
backward-compatible command construction.

Use `--export` to write the generated recipe to YAML instead of executing it:

```bash
fetchez build -R <W/E/S/N> --export pipeline.yaml tnm audit
```

The exported recipe can later be reproduced with:

```bash
fetchez run pipeline.yaml
```

### Component Discovery:

```text
fetchez modules list           List available data modules
fetchez modules bundles list   List curated data bundles
fetchez hooks list             List processing hooks
fetchez hooks presets list     List hook presets
```

Use any registered component directly in the build chain.
Run `fetchez build <component> --help` to inspect its component-specific options.


```{eval-rst}
.. click:: fetchez.cli:cli
   :nested: full
   :prog: fetchez
```
