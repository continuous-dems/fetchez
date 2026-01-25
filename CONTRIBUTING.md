# Contributing to GeoFetch

Thank you for considering contributing to GeoFetch! We welcome contributions from the community to help make geospatial data acquisition easier for everyone.

Whether you're fixing a bug, adding a new data module, or improving documentation, this guide will help you get started.

## 🛠️ Development Setup

1.  **Fork the Repository:** Click the "Fork" button on the top right of the GitHub page.
2.  **Clone your Fork:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/geofetch.git](https://github.com/YOUR_USERNAME/geofetch.git)
    cd geofetch
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
* (If possible) The specific region (`-R`) that caused the failure.

## 🚀 Adding a New Fetch Module

The most common contribution is adding support for a new data source.

1.  **Create the Module File:**
    Create a new Python file in `src/geofetch/modules/` (e.g., `mydata.py`).

2.  **Inherit from FetchModule:**
    Your class must inherit from `geofetch.core.FetchModule`.

    ```python
    from geofetch import core
    from geofetch import cli

    @cli.cli_opts(help_text="Fetch data from MyData Source")
    class MyData(core.FetchModule):
        def __init__(self, **kwargs):
            super().__init__(name='mydata', **kwargs)
            # Initialize your specific headers or API endpoints here

        def run(self):
            # 1. Construct the download URL based on self.region
            # 2. Use core.Fetch(url).fetch_file(...) to download it
            # 3. Add successful downloads to self.results
            pass
    ```

3. **Register the Module:**
Open src/geofetch/registry.py and add your module to the _modules dictionary. Please fill out all metadata fields to aid in data discovery.

Python

'mydata': {
    'mod': 'geofetch.modules.mydata', 
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

4.  **Test It:**
    Run `geofetch mydata --help` to ensure it loads correctly.

## 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:**
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `geofetch.spatial` helpers for region parsing; avoid manual coordinate unpacking.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source.
4.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").

## ⚖️ License

By contributing to GeoFetch, you agree that your contributions will be licensed under the MIT License.