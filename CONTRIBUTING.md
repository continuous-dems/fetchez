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
* (If possible) The specific region (`-R`) and module that caused the failure.

## 🐄 Developing User Plugins

One of the most powerful features of `fetchez` is its plugin architecture. You can write your own modules to fetch data from custom sources and use them immediately with the full power of the `fetchez` CLI (smart regions, threading, retries, etc.).

### How it Works
1.  `fetchez` scans `~/.fetchez/plugins/` at runtime.
2.  It loads any `.py` file it finds.
3.  It registers any class that inherits from `geofetch.core.FetchModule`.

### Example Plugin
Create a file named `~/.fetchez/plugins/my_uni.py`:

```python
from fetchez import core, cli

@cli.cli_opts(
    help_text="Fetch research data from University Servers",
    semester="Target semester (e.g., f2023, s2024)",
)
class MyUni(core.FetchModule):
    """My Custom Data Fetcher"""
    
    def __init__(self, semester='s2024', **kwargs):
        # The 'name' here becomes the CLI command
        super().__init__(name='my_uni', **kwargs)
        self.semester = semester
        
    def run(self):
        # Use self.region if spatial filtering is needed
        if self.region:
             print(f"Searching in region: {self.region}"

        # (This is where you'd usually hit an API or parse a directory)	

        url = f"https://data.uni.edu/{self.semester}/files.zip"
        self.add_entry_to_results(url, "data.zip", "zip")
    
```

#### Testing Your Plugin
Once you save the file, simply run:

```bash

# Check if it loaded
fetchez --modules | grep university_data

# or
fetchez --search plugin

# Run it
fetchez university_data --semester s2024
```

#### Promoting a Plugin
Did you build a plugin that would be useful for the wider community? We'd love to incorporate it!

Submit a Pull Request adding your file to geofetch/modules/.

Add a registry entry in geofetch/registry.py.

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

## 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:**
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source.
4.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").

## ⚖️ License

By contributing to Fetchez, you agree that your contributions will be licensed under the MIT License.