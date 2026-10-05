# 🪝 Developing User Hooks
Hooks allow you to inject custom processing into the `fetchez` pipeline. You can write hooks to process files immediately after they are downloaded, or to run setup/teardown tasks.

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
    meta_desc = "Log downloaded files to audit.txt"
    meta_stage = "file"  # Runs per-file

    def run(self, entries):
        # Hooks receive a list of entries: [{url, path, type, status}, ...]
        for entry in entries:
            url = entry.get("url")
            path = entry.get("dst_fn")
            status = entry.get("status")

            if status == 0:
                with open("audit.txt", "a") as f:
                    f.write(f"DOWNLOADED: {path} FROM {url}\n")

        # Always return the entries so the pipeline continues!
        return entries
```

## Testing Your Hook

```bash
# Check if it loaded
fetchez hooks list

# Run it
fetchez run srtm_plus --hook audit
```

## Developing & Sharing Presets
Presets (Macros) are the easiest way to share complex data engineering workflows without writing Python code. They allow you to bundle multiple processing steps into a single, shareable YAML snippet.

### The Preset Structure
Presets are standalone `.yaml` files placed in `~/.fetchez/presets/`. You can quickly see all active presets on your system by running `fetchez --list-presets`.

A preset requires a `name`, a `description`, and a list of `hooks` and their arguments.

`~/.fetchez/presets/clean_download.yaml`
```yaml
name: clean-download
description: "Unzip files and remove the original archive."
hooks:
  - name: unzip
    args:
      remove: true
```

### Module-Specific Overrides
Sometimes you build a macro that is only relevant to one specific dataset. For example, if you use the multibeam module, you might want a shortcut to only download the .inf metadata files.

You can restrict a preset so it only appears in the CLI menu for a specific module by adding the target_module key!

`~/.fetchez/presets/inf_only.yaml`

```yaml
name: inf_only
target_module: multibeam
description: 'multibeam Only: Fetch only inf files'
hooks:
  - name: filename_filter
    args:
      match: '.inf'
      stage: manifest
```
Now, `--inf-only` will show up when you run `fetchez multibeam --help`, but it won't clutter the global menu!

### Best Practices for Sharing
If you have developed a robust workflow (e.g., "Standard Archival Prep" or "Cloud Optimized GeoTIFF Conversion"), you can share it easily!

**Share the YAML:** You can post your .yaml file in a GitHub Issue or on our Zulip chat. Users can just drop it into their ~/.fetchez/hooks/presets/ folder.

**Bundle in a Python Package:** If you are building a Python package that extends `fetchez` (like `globato`), you can distribute presets automatically! Just place your YAML files in a package directory and register them in your pyproject.toml:

```toml
[project.entry-points."fetchez.hooks.presets"]
my_custom_presets = "my_package.hooks.presets"
```

**Contribute to Core:** If a preset is universally useful, you can propose adding it directly to the `fetchez/hooks/presets/` core directory via a Pull Request.

# 🔗 Sharing a Hook or Preset
Did you build a Hook or Preset that would be useful for the wider community? We'd love to incorporate it!

Submit a Pull Request adding your file to `fetchez/hooks/` or `fetchez/hooks/presets`.
