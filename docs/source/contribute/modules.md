# 🌎 Adding a New Fetch Module

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

## Handling Dependencies & Imports

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
