# 🐄 Plugins & Extensions

Fetchez is designed to be highly extensible. You can add **Modules**, **Bundles**, **Hooks**, **Presets**, **Readers**, **Profiles**, **Recipes**, **Modifiers**, and **Schemas** using the Fetchez registry system.

This makes it simple to create custom personal plugins for your own workflows, or to build widely distributed Fetchez extensions that others can install.

> **Running example:** Throughout the User Guide, we've shown you how to *use* the built-in `stac`, `copernicus`, `unzip`, and `audit` components. This page shows you how to **write your own** when the built-ins don't fit your needs.

## Two Ways to Extend Fetchez

There are two approaches, depending on your goals:

| Approach | Best for | Where it lives | Distribution |
|----------|----------|----------------|--------------|
| **Local Plugins** | Quick, personal scripts and configurations | `~/.fetchez/` folders | Personal use only |
| **Full Extensions** | Shareable packages for others to install | Your Python project | Via pip/conda |

Both approaches leverage the same registry system. Local plugins are faster to prototype; full extensions are better for collaboration.

---

## Local Plugins (Quick & Easy)

Local plugins are standalone Python scripts or YAML configuration files that you drop into your local `~/.fetchez` configuration folders. Fetchez automatically scans these folders at runtime and registers any valid plugins it finds.

### Data Modules and Bundles

Located in: `~/.fetchez/modules/` and `~/.fetchez/modules/bundles/`

Data Modules tell Fetchez how to talk to a specific API or how to find a particular data source.

To build one, create a Python script containing a class that inherits from `fetchez.modules.FetchModule`:

**Example:** Create `~/.fetchez/modules/my_server.py`:

```python
from fetchez.modules import FetchModule

class MyCustomServer(FetchModule):
    name = "my_server"
    meta_desc = "Fetches data from my local company server."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self):
        # Your custom logic to query an API and yield URLs goes here.
		self.add_entry_to_results({
            "url": "http://myserver.local/data.zip",
            "dst_fn": "data.zip"
        })
```

You can now run this directly from the CLI:

```bash
fetchez build -R 'loc:san diego, ca' my_server
```

### Processing Hooks and Presets

Located in: `~/.fetchez/hooks/` and `~/.fetchez/hooks/presets/`

Hooks intercept data before, during, or after the fetch process and do things to or with their attached module or to the global pool of data.

A hook should have a `run` method that accepts and returns the data `entries`, possibly transforming them along the way.

To build one, create a class that inherits from `fetchez.hooks.FetchHook`:

**Example:** Create `~/.fetchez/hooks/zulip_notify.py`:

```python
import logging
from fetchez.hooks import FetchHook

logger = logging.getLogger(__name__)

class ZulipNotifier(FetchHook):
    name = "zulip_notify"
    meta_stage = "post"
    meta_category = "comms"

    def __init__(self, chan="fetchez", **kwargs):
        super().__init__(**kwargs)
        self.chan = chan

    def run(self, entries):
        import zulip
        client = zulip.Client()
        mods = set()
        for mod, entry in entries:
            mods.add(mod)

        params = {
            "type": "stream",
            "to": self.chan,
            "topic": "Auto-Fetchez",
            "content": f"Downloaded {len(entries)} files from {len(mods)} modules."
        }
        result = client.send_message(params)
        logger.info(f"Zulip notification result: {result.get('result')}!")
        return entries
```

You can now use this in your presets, recipes, and CLI commands:

```bash
fetchez build copernicus zulip_notify
```

### Streams, Readers, and Profiles

Located in: `~/.fetchez/streams/readers/` and `~/.fetchez/streams/profiles/`

Custom readers and profiles let you decode data formats that Fetchez doesn't natively support. See [Streams & Readers](streams.md) for implementation details.

### Using Local Plugins

Once your plugin is in place, verify it's registered:

```bash
fetchez modules list     # Should include my_server
fetchez hooks list       # Should include zulip_notify
```

Plugins are loaded dynamically at runtime — no reinstall needed. Just drop the file in and refresh.

---

## Full Extensions (Distributable Packages)

Full extensions are proper Python packages that register their components via `pyproject.toml` entry points. Others can install them via pip or conda, and they'll appear alongside Fetchez's built-in components.

### Project Structure

For a package laid out with corresponding importable subpackages:

```
my_project/
├── pyproject.toml
└── my_project/
    ├── __init__.py
    ├── modules/
    │   ├── __init__.py
    │   └── custom_source.py
    ├── hooks/
    │   ├── __init__.py
    │   └── custom_hook.py
    ├── streams/
    │   ├── readers/
    │   └── profiles/
    └── recipes/
        ├── example.yaml
        ├── modifiers/
        └── schemas/
```

### Declaring Entry Points

In `pyproject.toml`, declare the components your package provides:

**Modules**

```toml
[project.entry-points."fetchez.modules"]
my_project_modules = "my_project.modules"
```

**Bundles**

```toml
[project.entry-points."fetchez.modules.bundles"]
my_project_bundles = "my_project.modules.bundles"
```

**Hooks**

```toml
[project.entry-points."fetchez.hooks"]
my_project_hooks = "my_project.hooks"
```

**Presets**

```toml
[project.entry-points."fetchez.hooks.presets"]
my_project_presets = "my_project.hooks.presets"
```

**Streams**

```toml
[project.entry-points."fetchez.streams"]
my_project_streams = "my_project.streams"
```

**Stream Readers**

```toml
[project.entry-points."fetchez.streams.readers"]
my_project_readers = "my_project.streams.readers"
```

**Stream Profiles**

```toml
[project.entry-points."fetchez.streams.profiles"]
my_project_profiles = "my_project.streams.profiles"
```

**Recipes**

```toml
[project.entry-points."fetchez.recipes"]
my_project_recipes = "my_project.recipes"
```

**Modifiers**

```toml
[project.entry-points."fetchez.recipes.modifiers"]
my_project_modifiers = "my_project.recipes.modifiers"
```

**Schemas**

```toml
[project.entry-points."fetchez.recipes.schemas"]
my_project_schemas = "my_project.recipes.schemas"
```

### Distributing Your Extension

Once packaged, users install it with pip:

```bash
pip install my-project-fetchez
```

All your registered components will appear in `fetchez modules list`, `fetchez hooks list`, etc., just like the built-ins.

---

## What Can You Extend?

| Component | Purpose | Local Plugin Location | Extension Entry Point |
|-----------|---------|----------------------|----------------------|
| Modules | Data sources | `~/.fetchez/modules/` | `fetchez.modules` |
| Bundles | Groups of modules | `~/.fetchez/modules/bundles/` | `fetchez.modules.bundles` |
| Hooks | Processing steps | `~/.fetchez/hooks/` | `fetchez.hooks` |
| Presets | Hook macros | `~/.fetchez/hooks/presets/` | `fetchez.hooks.presets` |
| Readers | Data decoders | `~/.fetchez/streams/readers/` | `fetchez.streams.readers` |
| Profiles | Reader configs | `~/.fetchez/streams/profiles/` | `fetchez.streams.profiles` |
| Recipes | Workflow definitions | `~/.fetchez/recipes/` | `fetchez.recipes` |
| Modifiers | Runtime transformers | `~/.fetchez/recipes/modifiers/` | `fetchez.recipes.modifiers` |
| Schemas | Validation rules | `~/.fetchez/recipes/schemas/` | `fetchez.recipes.schemas` |

---

## When to Write Custom Code

Before writing a custom module, hook, or reader, consider whether a generic module or existing configuration might suffice:

1. **Can a generic module handle it?** (`stac`, `rest_api`, `http_index`, `thredds`)
2. **Can configuration solve it?** (YAML bundles, presets, profiles)
3. **Do you need specialized discovery or processing logic?** → Write custom code

If you genuinely need custom code, Fetchez provides registries and execution lifecycles for:

* **Modules and bundles** — discover data sources and curate reusable collections
* **Hooks and presets** — inspect, filter, transform, and process entries, files, and streams
* **Readers and streams** — connect acquired data with downstream processing
* **Recipes, modifiers, and schemas** — compose, customize, and validate repeatable workflows
* **Plugins and extensions** — add domain-specific behavior without changing Fetchez core

The goal is to make useful workflows easy to **discover, reproduce, adapt, and share** — whether through a one-file local plugin or a full distributable extension.

---

## Contributing Upstream

If you've built something that might benefit the broader Fetchez community, consider contributing it upstream:

* Open a GitHub issue to discuss your idea first
* Submit a pull request with your custom module, hook, or documentation
* Participate in the [community chat](https://cudem.zulip.org/) for design discussions

See the [Contributor Guide](../contribute/index.md) for detailed instructions on development setup, testing requirements, and contribution workflow.

---

**Next up:** If you're ready to contribute to Fetchez itself, head to the [Contributor Guide](../contribute/index.md). Otherwise, review the [Data Persistence disclaimer](data_persistence.md) for important information about data reliability.
