# Contributing to Fetchez

Thank you for considering contributing to Fetchez! We welcome contributions from the community to help make geospatial data acquisition easier for everyone.

Whether you're fixing a bug, adding a new data module, or improving documentation, this guide will help you get started.

## 🛠️ Development Setup

1.  **Fork the Repository:** Click the "Fork" button on the top right of the GitHub page.
2.  **Clone your Fork:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/fetchez.git
    cd fetchez
    ```
3.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
4.  **Install in Editable Mode:**
    ```bash
    pip install -e .
    ```

## 🐛 Reporting Bugs


If you find a bug, please create a new issue on GitHub. Include:
* The exact command you ran.
* The error message / traceback.
* Your operating system and Python version.

## 🐄 Developing User Plugins (Data Modules)

One of the most powerful features of `fetchez` is its plugin architecture. You can write your own modules to fetch data from custom sources and use them immediately with the full power of the `fetchez` CLI (smart regions, threading, retries, etc.).

### How it Works
1.  `fetchez` scans `~/.fetchez/plugins/` at runtime.
2.  It loads any `.py` file it finds.
3.  It registers any class that inherits from `fetchez.core.FetchModule`.

### Example Plugin
Create a file named `~/.fetchez/plugins/usgs_checkpoints.py`:

```python
from fetchez import core, cli

checkpoints_base_url = 'https://www.sciencebase.gov/catalog/file/get/'
checkpoints_link = '67075e6bd34e969edc59c3e7?f=__disk__80%2F12%2F9e%2F80129e86d18461ed921b288f13e08c62e8590ffb'

@cli.cli_opts(help_text="USGS Elevation Checkpoints")
class CheckPoints3DEP(core.FetchModule):
    def __init__(self, **kwargs):
    	# `name` here becomes the name of fetchez module in the cli
        super().__init__(name='my_checkpoints', **kwargs)
        
    def run(self):
        # Use self.region if spatial filtering is needed
        if self.region:
             print(f"Searching in region: {self.region}"

    	# This is where you'd normally hit an API, or parse some
        # data, etc.
	
        self.add_entry_to_results(
            url=f'{checkpoints_url}{checkpoints_link}',
            dst_fn='USGS_CheckPoints.zip',
            data_type='checkpoints',
        )            
```

### Testing Your Plugin
Once you save the file, simply run:

```bash

# Check if it loaded
fetchez --modules | grep my_checkpoints

# or
fetchez --search plugin

# Run it
fetchez my_checkpoints
```

## 🪝 Developing User Hooks (Processing)
Hooks allow you to inject custom processing into the fetch pipeline. You can write hooks to process files immediately after they are downloaded, or to run setup/teardown tasks.

### How it Works

fetchez scans ~/.fetchez/hooks/ at runtime.

It registers any class that inherits from fetchez.hooks.FetchHook.

### Example Hook
Create a file named ~/.fetchez/hooks/audit_log.py to log every download to a file:

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

### Testing Your Hook

```bash
# Check if it loaded
fetchez --list-hooks

# Run it
fetchez srtm_plus --hook audit
```

#### Promoting a Plugin or Hook
Did you build a plugin that would be useful for the wider community? We'd love to incorporate it!

Submit a Pull Request adding your file to fetchez/modules/ or fetchez/hooks.

## 🌎 Adding a New Fetch Module

The most common contribution is adding support for a new data source.

1.  **Create the Module File:**
    Create a new Python file in `src/fetchez/modules/` (e.g., `mydata.py`).

2.  **Inherit from FetchModule:**
    Your class must inherit from `fetchez.core.FetchModule`.

    ```python
    from fetchez import core
    from fetchez import cli

    @cli.cli_opts(help_text="Fetch data from MyData Source")
    class MyData(core.FetchModule):
        def __init__(self, **kwargs):
            super().__init__(name='mydata', **kwargs)
            # Initialize your specific headers or API endpoints here

        def run(self):
            # 1. Construct the download URL based on self.region
            # 2. Use core.Fetch(url).fetch_req(...) to query the API for download urls
            # 3. Add successful download urls to the results with `self.add_entry_to_results'
            pass
    ```

3. **Register the Module:**
Open src/fetchez/registry.py and add your module to the _modules dictionary. Please fill out all metadata fields to aid in data discovery.

```python

'mydata': {
    'mod': 'fetchez.modules.mydata', 
    'cls': 'MyData', 
    'category': 'Topography',
    'desc': 'Short summary of the dataset (e.g. Global Lidar Synthesis)',
    'agency': 'Provider Name (e.g. USGS, NOAA)',
    'tags': ['lidar', 'elevation', 'high-res'],
    'region': 'Coverage Area (e.g. CONUS, Global)',
    'resolution': 'Nominal Resolution (e.g. 1m)',
    'license': 'License Type (e.g. Public Domain, CC-BY)',
    'urls': {
        'home': '[https://provider.gov/data](https://provider.gov/data)',
        'docs': '[https://provider.gov/docs](https://provider.gov/docs)'
    }
},
```

4.  **Test It:**
    Run `fetchez mydata --help` to ensure it loads correctly.

### Handling Dependencies & Imports

Fetchez aims to keep its core footprint small. If your new module or plugin requires a non-standard library (e.g., `boto3`, `pyshp`, `netCDF4`):

1.  **Do Not Add to Core Requirements:** Do not add the library to `pyproject.toml` unless it is essential for the entire `fetchez` engine.
2.  **Soft Imports:** Wrap your imports in a `try/except ImportError` block so the module does not crash the CLI for users who don't use that specific data source.
3.  **Document It:** Clearly list the required packages in the class docstring.

**Example:**

```python
try:
    import boto3
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

@cli.cli_opts(help_text="Fetch data from AWS")
class MyS3Fetcher(core.FetchModule):
    """Fetches data from private S3 buckets.

    **Dependencies:**
    This module requires `boto3`. Install it via:
    `pip install boto3`
    """
    
    def run(self):
        if not HAS_BOTO:
            # Use the logger to inform the user nicely
            logger.error("This module requires 'boto3'. Please install it to proceed.")
            return
        
        # Proceed with fetching...
```

## 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:**
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source.
4.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").
5.  **Pull Request:** Make a pull request to merge your branch into main.

## ⚖️ License

* **Core Contributions:** By contributing to this repository (including new modules in fetchez/modules/), you agree that your contributions will be licensed under the project's MIT License. You retain your individual copyright to your work, but you grant the project a perpetual, non-exclusive right to distribute it under the MIT terms.

* **External Plugins:** If you develop a module as an external user plugin (e.g., loaded from ~/.fetchez/plugins/ and not merged into this repository), you are free to license it however you wish.
