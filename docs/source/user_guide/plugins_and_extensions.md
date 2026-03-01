# 🐄 Plugins & Extensions

Need to fetch data from a specialized local server? Or maybe run a custom script immediately after every download? You don't need to fork the repo!

There are two ways to extend Fetchez: **Local Plugins** (for quick, personal scripts) and **Full Extensions** (for distributable Python packages).

##  Local Plugins (Quick & Easy)

Local plugins are standalone Python scripts that you drop into your local Fetchez configuration folders. Fetchez automatically scans these folders at runtime and registers any valid classes it finds.

### Data Modules (`~/.fetchez/plugins/`)
Data Modules tell Fetchez how to talk to a specific API or data source.

To build one, create a Python script containing a class that inherits from `fetchez.core.FetchModule`.

**Example:**

Create `~/.fetchez/plugins/my_server.py`:
```python
from fetchez.core import FetchModule

class MyCustomServer(FetchModule):
    name = "my_server"

    def run(self):
        # Your custom logic to query an API and yield URLs goes here.
        self.results.append({
            "url": "http://myserver.local/data.zip",
            "dst_fn": "data.zip"
        })
```

You can now run this instantly from the CLI: fetchez my_server

### Processing Hooks (~/.fetchez/hooks/)
Hooks intercept data before, during, or after the fetch process.

To build one, create a class that inherits from fetchez.hooks.FetchHook.

**Example:**

Create ~/.fetchez/hooks/notify.py:
```python
from fetchez.hooks import FetchHook

class ZulipNotifier(FetchHook):
    name = "zulip_notify"
    stage = "post" # Runs after all downloads finish

    def run(self, entries):
        # Code to ping a webhook
        print(f"Notified Zulip that {len(entries)} files were downloaded!")
        return entries
```

You can now use this in your recipes and cli switches: `fetchez copernicus --hook zulip_notify`
