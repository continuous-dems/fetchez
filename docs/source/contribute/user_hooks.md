# 🪝 Developing User Hooks
Hooks allow you to inject custom processing into the fetch pipeline. You can write hooks to process files immediately after they are downloaded, or to run setup/teardown tasks.

## How it Works

`fetchez` scans `~/.fetchez/hooks/` at runtime.

It registers any class that inherits from `fetchez.hooks.FetchHook`.

## Example Hook
Create a file named `~/.fetchez/hooks/audit_log.py` to log every download to a file:

```python
import os
from fetchez.hooks import FetchHook

class AuditLog(FetchHook):
    # This name is used in the CLI: --hook audit
    name = "audit"
    desc = "Log downloaded files to audit.txt"
    stage = 'file'  # Runs per-file

    def run(self, entries):
        # Hooks receive a list of entries: [{url, path, type, status}, ...]
        for entry in entries:
            url = entry.get('url')
            path = entry.get('dst_fn')
            status = entry.get('status')

            if status == 0:
                with open("audit.txt", "a") as f:
                    f.write(f"DOWNLOADED: {path} FROM {url}\n")

        # Always return the entries so the pipeline continues!
        return entries
```

## Testing Your Hook

```bash
# Check if it loaded
fetchez --list-hooks

# Run it
fetchez srtm_plus --hook audit
```

# 🤝 Sharing a Plugin or Hook
Did you build a plugin that would be useful for the wider community? We'd love to incorporate it!

Submit a Pull Request adding your file to fetchez/modules/ or fetchez/hooks.

## 🔗 Developing & Sharing Presets
Presets (or "Macros") are the easiest way to share complex data engineering workflows without writing Python code. They allow you to bundle multiple processing steps into a single, shareable YAML snippet.

### The Preset Configuration File

Presets are stored in `~/.fetchez/presets.yaml`. You can generate a valid template using `fetchez --init-presets`.

The file has two main sections:

* Global Presets: Macros available for every module.

* Module Presets: Macros that only appear when using a specific module.

presets.yaml Example

```yaml
presets:
  audit-full:
    help: Generate SHA256 hashes, enrichment, and a full JSON audit log.
    hooks:
    - name: checksum
      args:
        algo: sha256
    - name: enrich
    - name: audit
      args:
        file: audit_full.json
  clean-download:
    help: Unzip files and remove the original archive.
    hooks:
    - name: unzip
      args:
        remove: 'true'
```

***Best Practices for Sharing***

If you have developed a robust workflow (e.g., "Standard Archival Prep" or "Cloud Optimized GeoTIFF Conversion", or whatever), you can share it easily!

* Test your preset: Ensure the hooks run in the correct order (e.g., unzip before filter).

* Add a Help String: The "help" field in the YAML is displayed in the CLI when users run `fetchez --help`. Make it descriptive if you can!

* Share the YAML: You can post your YAML snippet in a GitHub Issue or Discussion or on our [Zulip chat](https://cudem.zulipchat.com/).

* Contribute to Core: If a preset is universally useful, you can propose adding it to the `init_presets()` function in `fetchez/presets.py` via a Pull Request.

***Module-Specific Overrides***

You can use the modules section to create specialized shortcuts for specific datasets.

For example, you often use fetchez dav (NOAA Digital Coast) but only want to check if data exists without downloading gigabytes of lidar. Now, you can create a preset that filters for "footprint" files only by writing a series of hooks and then combining them into a preset. Then, when you run `fetchez dav --help`, you will see your custom `--footprint-only` flag listed under "DAV Presets", but it won't clutter the menu for other modules.
