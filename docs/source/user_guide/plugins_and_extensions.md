# 🐄 Plugins & Extensions

Fetchez is designed to be highly extendable. Fetchez can extended by adding Modules, Bundles, Hooks, Presets, Readers, Profiles, Recipes, Modifiers and Schemas. Using the fetchez registry system, its simple to create custom personal plugins or widely distributed Fetchez extensions.

There are two ways to extend `fetchez`: **Local Plugins** (for quick, personal scripts and plugins) and **Full Extensions** (for distributable Python packages).

##  Local Plugins (Quick & Easy)

Local plugins are standalone Python scripts or YAML configuration files that you drop into your local `~/.fetchez` configuration folders. Fetchez automatically scans these folders and endpoints at runtime and registers any valid plugins it finds.

### Data Modules and Bundles
Located in: `~/.fetchez/modules/` and `~/.fetchez/modules/bundles`

Data Modules tell Fetchez how to talk to a specific API or how to find a particular data source.

To build one, create a Python script containing a class that inherits from `fetchez.modules.FetchModule`.

**Example:**

Create `~/.fetchez/modules/my_server.py`:
```python
from fetchez.modules import FetchModule

class MyCustomServer(FetchModule):
    name = "my_server"
	meta_desc = "Fetches data from my local company server."

	def __init__(self, **kwargs):
		super().__init__(name="my_server", **kwargs)

    def run(self):
        # Your custom logic to query an API and yield URLs goes here.
        self.results.append({
            "url": "http://myserver.local/data.zip",
            "dst_fn": "data.zip"
        })
```

You can now run this instantly from the CLI: `fetchez run my_server`

### Processing Hooks and Presets
Located in: `~/.fetchez/hooks/` and `~/.fetchez/hooks/presets`

Hooks intercept data before, during, or after the fetch process and do things to or with their attached module or to the global pool of data.

A hook should have a `run` method that accepts and retuns the data `entries`, possibly doing something to/with those entries along the way.

To build one, create a class that inherits from `fetchez.hooks.FetchHook`.

**Example:**

Create ~/.fetchez/hooks/zulip_notify.py:
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

You can now use this in your presets, recipes and cli commands: `fetchez run copernicus --hook zulip_notify`

> Next up: Ready to make custom modules, hooks and recipes? Want to contribute to the Fetchez ecosystem? See the [Contributor Guide](/contribute/index.md) for information on how to do so!
