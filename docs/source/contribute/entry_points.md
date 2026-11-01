# 📦 Entry Points

Fetchez discovers components through Python package entry points. When you build a distributable extension, declaring the right entry points in `pyproject.toml` ensures that your modules, hooks, readers, and other components are automatically registered and available alongside Fetchez's built-ins.

This page covers **distribution entry points** — the configuration needed to ship your extensions as installable packages. For local plugins (non-distributable), see [User Plugins](user_plugins.md).

> **Note:** There is also an internal concept of *Fetchez entries* — the data objects that flow through pipelines. For architecture documentation on entries, see [Architecture](architecture.md).

## What Are Entry Points?

Entry points are a Python packaging mechanism that allows packages to declare that they provide certain functionality. At runtime, Fetchez scans installed packages for its registered entry points and loads any components found there.

When you install a Fetchez extension via pip or conda:

1. Python's packaging system reads the entry point declarations in `pyproject.toml`
2. The entry point groups (e.g., `fetchez.modules`) are registered in the environment
3. Fetchez queries the registry to discover all installed components
4. Your modules, hooks, and other components appear in `fetchez modules list`, `fetchez hooks list`, etc.

No manual registration or configuration is required by the end user.

## All Fetchez Entry Point Groups

Fetchez recognizes the following entry point groups. Declare the ones that apply to your extension:

| Component Type | Entry Point Group | What It Registers |
|----------------|-------------------|-------------------|
| Modules | `fetchez.modules` | Data source modules (Python classes) |
| Bundles | `fetchez.modules.bundles` | YAML bundle definitions |
| Hooks | `fetchez.hooks` | Processing hooks (Python classes) |
| Presets | `fetchez.hooks.presets` | YAML hook macro definitions |
| Streams | `fetchez.streams` | Stream classes |
| Stream Readers | `fetchez.streams.readers` | Reader implementations (Python classes) |
| Stream Profiles | `fetchez.streams.profiles` | YAML profile definitions |
| Recipes | `fetchez.recipes` | YAML recipe definitions |
| Modifiers | `fetchez.recipes.modifiers` | Modifier implementations (Python classes) |
| Schemas | `fetchez.recipes.schemas` | Schema implementations (Python classes) |

## Minimal Entry Point Declarations

For each component type you provide, add the corresponding entry point to `pyproject.toml`.

### Modules

```toml
[project.entry-points."fetchez.modules"]
my_project_modules = "my_project.modules"
```

### Bundles

```toml
[project.entry-points."fetchez.modules.bundles"]
my_project_bundles = "my_project.modules.bundles"
```

### Hooks

```toml
[project.entry-points."fetchez.hooks"]
my_project_hooks = "my_project.hooks"
```

### Presets

```toml
[project.entry-points."fetchez.hooks.presets"]
my_project_presets = "my_project.hooks.presets"
```

### Streams

```toml
[project.entry-points."fetchez.streams"]
my_project_streams = "my_project.streams"
```

### Stream Readers

```toml
[project.entry-points."fetchez.streams.readers"]
my_project_readers = "my_project.streams.readers"
```

### Stream Profiles

```toml
[project.entry-points."fetchez.streams.profiles"]
my_project_profiles = "my_project.streams.profiles"
```

### Recipes

```toml
[project.entry-points."fetchez.recipes"]
my_project_recipes = "my_project.recipes"
```

### Modifiers

```toml
[project.entry-points."fetchez.recipes.modifiers"]
my_project_modifiers = "my_project.recipes.modifiers"
```

### Schemas

```toml
[project.entry-points."fetchez.recipes.schemas"]
my_project_schemas = "my_project.recipes.schemas"
```

## Project Layout

Organize your package so that entry points map cleanly to importable subpackages:

```
my-project-fetchez/
├── pyproject.toml
├── README.md
└── my_project/
    ├── __init__.py
    ├── modules/
    │   ├── __init__.py
    │   ├── custom_source.py      # Python module classes
    │   └── another_source.py
    ├── modules/bundles/           # Optional: bundle YAML files
    │   ├── my_bundle.yaml
    │   └── another_bundle.yaml
    ├── hooks/
    │   ├── __init__.py
    │   ├── custom_hook.py        # Python hook classes
    │   └── notifier.py
    ├── hooks/presets/             # Optional: preset YAML files
    │   ├── audit_full.yaml
    │   └── checksum_all.yaml
    ├── streams/
    │   ├── __init__.py
    │   ├── readers/
    │   │   ├── __init__.py
    │   │   └── custom_reader.py  # Python reader classes
    │   └── profiles/              # Optional: profile YAML files
    │       ├── custom_csv.yaml
    │       └── icesat_profile.yaml
    ├── recipes/
    │   ├── example_recipe.yaml
    │   ├── modifiers/
    │   │   ├── __init__.py
    │   │   └── custom_modifier.py
    │   └── schemas/
    │       ├── __init__.py
    │       └── validation_schema.py
    └── tests/
        └── ...
```

## Complete Example: `pyproject.toml`

Here's a full `pyproject.toml` for an extension that provides modules, hooks, and readers:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-project-fetchez"
version = "0.1.0"
description = "Fetchez extension for XYZ data sources"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fetchez>=1.0",
    "requests>=2.28",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "black>=23.0",
    "mypy>=1.0",
]

[project.entry-points."fetchez.modules"]
my_project_modules = "my_project.modules"

[project.entry-points."fetchez.modules.bundles"]
my_project_bundles = "my_project.modules.bundles"

[project.entry-points."fetchez.hooks"]
my_project_hooks = "my_project.hooks"

[project.entry-points."fetchez.hooks.presets"]
my_project_presets = "my_project.hooks.presets"

[project.entry-points."fetchez.streams.readers"]
my_project_readers = "my_project.streams.readers"

[project.entry-points."fetchez.streams.profiles"]
my_project_profiles = "my_project.streams.profiles"
```

## Verifying Your Entry Points

After installing your extension (even in development mode), verify that Fetchez sees your components:

```bash
# Install in editable mode
pip install -e .

# Verify components are registered
fetchez modules list      # Should include your modules
fetchez hooks list        # Should include your hooks
fetchez hooks presets list  # Should include your presets
fetchez streams list      # Should include your streams/readers
```

If a component doesn't appear:

1. Ensure the entry point declaration matches the actual subpackage path
2. Check that the subpackage contains `__init__.py`
3. Verify the component class is properly decorated or named
4. Reinstall: `pip install -e . --force-reinstall`

## Local Plugins vs. Distribution Entry Points

Not everything needs an entry point! For personal or team use, you can skip packaging entirely:

| Approach | How It Works | Best For |
|----------|--------------|----------|
| **Entry points** | Declared in `pyproject.toml`; loaded via pip install | Sharing with others; version-controlled packages |
| **Local plugins** | Drop YAML/Python files into `~/.fetchez/` folders | Rapid prototyping; one-off customizations |

See [User Plugins](user_plugins.md) for the local plugin workflow.

## Testing Your Extension

Before distributing, test thoroughly:

1. **Fresh installation** — Create a clean virtual environment and install from scratch
2. **Component discovery** — Run `fetchez modules list`, `fetchez hooks list`, etc.
3. **End-to-end pipeline** — Use your modules/hooks in a real workflow
4. **Conflicts** — Verify no naming collisions with existing Fetchez components

## Publishing Your Extension

Once tested, publish to PyPI or conda-forge:

```bash
# Build distributions
python -m build

# Upload to PyPI
twine upload dist/*
```

Or submit to conda-forge following their guidelines.

---

## Related Documentation

* **[User Plugins](user_plugins.md)** — Creating local, non-distributed plugins
* **[Architecture](architecture.md)** — Understanding Fetchez's internal architecture
* **[Modules](modules.md)** — Writing custom data source modules
* **[Hooks](user_hooks.md)** — Implementing processing hooks
* **[Streams](../user_guide/streams.md)** — Custom readers and profiles

---

**Next up:** See [Modules](modules.md) to learn how to implement custom data source modules.
