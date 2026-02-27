# 🪝 Hooks, Presets, and Plugins

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
🔗 Pipeline Presets (Macros)
Tired of typing the same chain of hooks every time? Presets allow you to define reusable workflow macros.

Instead of running this long command:

Bash
fetchez copernicus --hook checksum:algo=sha256 --hook enrich --hook audit:file=log.json
You can define a preset and simply run:

Bash
fetchez copernicus --audit-full
How to create a Preset:
Initialize your config: Run this command to generate a starter configuration file at ~/.fetchez/presets.json:

Bash
fetchez --init-presets
Define your workflow: Edit the JSON file to create a named preset. A preset is just a list of hooks with arguments.

JSON
"my-clean-workflow": {
  "help": "Unzip files and immediately remove the zip archive.",
  "hooks": [
    {"name": "unzip", "args": {"remove": "true"}},
    {"name": "pipe"}
  ]
}
Run it: Your new preset automatically appears as a CLI flag!

Bash
fetchez charts --my-clean-workflow
🐄 Plugins & Extensions (Bring Your Own Code)
Need to fetch data from a specialized local server? Or maybe run a custom script immediately after every download? You don't need to fork the repo!

Fetchez is designed to be extendable in two ways:

Data Modules (~/.fetchez/plugins/): Add new data sources or APIs.

Processing Hooks (~/.fetchez/hooks/): Add new pre, file, or post-processing steps.

Drop your Python scripts into these configuration folders, and they will be automatically registered as native commands.

Quick Start:

Create the folder: mkdir ~/.fetchez/plugins

Drop a python script there (e.g., my_data.py containing a class that inherits from FetchModule).

Run it: fetchez my_data