# Contributing to Fetchez

Thank you for considering contributing to Fetchez! We welcome contributions from the community to help make geospatial data acquisition easier for everyone.

Whether you're fixing a bug, adding a new data module, or improving documentation, this guide will help you get started.

## 🛠️Development Setup

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

## 📚 Improving Documentation & Examples

Great documentation is just as important as code! We want Fetchez to be accessible to everyone, from students to seasoned geospatial engineers.

**How you can help:**
* **Fix Typos & Clarity:** Found a confusing sentence in the README or a typo in a docstring? Please fix it! Small changes make a big difference.
* **Add Examples:** Have a cool workflow? (e.g. *"Fetching and gridding lidar data with PDAL"* or *"Automating bathymetry updates"*). Share it!
    * Create a Jupyter Notebook, a Markdown tutorial, or a simple shell script.
    * Submit it to the `examples/` directory via a Pull Request.
* **Improve Module Docs:** Many modules could use better descriptions or more usage examples in their help text.
    * Update the `help_text` in the module's `@cli.cli_opts` decorator.
    * Update the class docstring with specific details about the dataset (resolution, vertical datum, etc.).




```

*** Best Practices for Sharing ***

If you have developed a robust workflow (e.g., "Standard Archival Prep" or "Cloud Optimized GeoTIFF Conversion", or whatever), you can share it easily!

* Test your preset: Ensure the hooks run in the correct order (e.g., unzip before filter).

* Add a Help String: The "help" field in the JSON is displayed in the CLI when users run `fetchez --help`. Make it descriptive if you can!

* Share the YAML: You can post your YAML snippet in a GitHub Issue or Discussion or on our Zulip chat.

* Contribute to Core: If a preset is universally useful, you can propose adding it to the `init_presets()` function in `fetchez/presets.py` via a Pull Request.

***Module-Specific Overrides***

You can use the modules section to create specialized shortcuts for specific datasets.

For example, you often use fetchez dav (NOAA Digital Coast) but only want to check if data exists without downloading gigabytes of lidar. Now, you can create a preset that filters for "footprint" files only by writing a series of hooks and then combining them into a preset. Then, when you run `fetchez dav --help`, you will see your custom `--footprint-only` flag listed under "DAV Presets", but it won't clutter the menu for other modules.

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

1.  **Do Not Add to Core Requirements:** Do NOT add the library to the main `dependencies` list in `pyproject.toml`.
2.  **Add to Optional Dependencies:** Open `pyproject.toml` and add your library to a relevant group under `[project.optional-dependencies]`. If no group fits, create a new one (e.g. `netcdf = ["netCDF4"]`).
3.  **Soft Imports:** Wrap your imports in a `try/except ImportError` block so the module does not crash the CLI for users who don't use that specific data source.
4.  **Document It:** Clearly list the required packages (and the install command) in the class docstring.

**Example:**

```python
# fetchez/modules/mys3.py

try:
    import boto3
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

@cli.cli_opts(help_text="Fetch data from AWS")
class MyS3Fetcher(core.FetchModule):
    """Fetches data from private S3 buckets.

    **Dependencies:**
    This module requires `boto3`.
    Install via: `pip install "fetchez[aws]"`
    """

    def run(self):
        if not HAS_BOTO:
            logger.error("Missing dependency 'boto3'. Please run: pip install 'fetchez[aws]'")
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

## ⚖ License

* **Core Contributions:** By contributing to this repository (including new modules in fetchez/modules/), you agree that your contributions will be licensed under the project's MIT License. You retain your individual copyright to your work, but you grant the project a perpetual, non-exclusive right to distribute it under the MIT terms.

* **External Plugins:** If you develop a module as an external user plugin (e.g., loaded from ~/.fetchez/plugins/ and not merged into this repository), you are free to license it however you wish.


```{toctree}
:maxdepth: 2

user_plugins
user_hooks
```