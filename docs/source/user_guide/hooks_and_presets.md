# 🪝 Hooks and Presets

Fetchez is designed to be highly extendable. Instead of just downloading files, you can build automated pipelines that process data on the fly.

## Processing Hooks

Fetchez includes a powerful **Hook System** that allows you to chain actions together. Hooks run in a pipeline, meaning the output of one hook (e.g., unzipping a file) becomes the input for the next (e.g., streaming and processing it).

There are three stages in the Hook lifecycle:
1. **PRE Stage:** Runs before any data is downloaded (e.g., filtering URLs, masking regions).
2. **FILE Stage:** Runs on each individual file as it is downloaded (e.g., unzipping, converting formats, or piping to stdout).
3. **POST Stage:** Runs after all files are downloaded (e.g., merging grids, calculating checksums).

### Common Built-in Hooks:
* `unzip`: Automatically extracts `.zip` or `.gz` files.
* `pipe`: Prints the final absolute path to stdout (useful for piping to GDAL/PDAL).
* `audit`: Generates a JSON manifest of everything downloaded and processed.

### Example (CLI):
```bash
# Download data.zip
# Extract data.tif (via unzip hook)
# Print /path/to/data.tif (via pipe hook)
fetchez charts --hook unzip --hook pipe
```

## Pipeline Presets (Macros)

Tired of typing the same chain of hooks every time? Presets allow you to define reusable workflow macros.

Instead of running this long command:

```bash
fetchez copernicus --hook checksum:algo=sha256 --hook enrich --hook audit:file=log.json
```

You can define a preset and simply run:

```bash
fetchez copernicus --audit-full
```

### How to create a Preset:

* **Initialize your config:** Run this command to generate a starter configuration file at `~/.fetchez/presets.yaml`:

```bash
fetchez --init-presets
```

* **Define your workflow:** Edit the `YAML` file to create a named preset. A preset is just a list of hooks with arguments.

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

**Run it:** Your new preset automatically appears as a CLI flag!

```bash
fetchez charts --audit-full --clean-download
```
