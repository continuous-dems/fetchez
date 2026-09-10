# 🌎 Adding a New Fetch Module

The most common contribution is adding support for a new data source. Because Fetchez uses dynamic discovery, you do not need to register your module in any central repository!

## 🏛️ Core vs. Extensions: Where should my module live?
Before submitting a Pull Request, consider whether your module belongs in the `fetchez` core repository or in a dedicated extension (like `globato` or your own custom Python package).

* **Lightweight Core:** The `fetchez` core repository acts strictly as a universal orchestrator. Modules submitted to core should be as lightweight as possible—essentially just "scan an API and return endpoints."
* **Heavy Extensions:** Not every new module needs to go into `fetchez`! If your module requires heavy, domain-specific processing (e.g., complex Shapely footprint intersections, bespoke provider naming rules, or unique CLI flags), it is better suited for an extension. Because of dynamic discovery, extension packages can host and register their own `FetchModule` classes that integrate seamlessly into the user's CLI alongside the core modules.

---

## 🛠️ Steps to Create a Module

1.  **Create the Module File:**
    Create a new Python file in `src/fetchez/modules/` (e.g., `mydata.py`).

2.  **Inherit from FetchModule:**
    Your class must inherit from `fetchez.modules.FetchModule`. You must define the `meta_` class attributes so the CLI and API can discover and index your module. Be sure to include all the relevant metadata for posterity and discoverability.

    ```python
    from fetchez.modules import FetchModule
    from fetchez import cli

    @cli.cli_opts(help_text="Fetch data from MyData Source")
    class MyData(FetchModule):

        name = "mydata"
        meta_category = "Topography"
        meta_desc = "Short summary of the dataset (e.g., Global Lidar Synthesis)"
        meta_agency = "Provider Name (e.g., USGS, NOAA)"
        meta_tags = ["lidar", "elevation", "high-res"]
        meta_coverage = "Coverage Area (e.g., CONUS, Global)"
        meta_resolution = "Nominal Resolution (e.g., 1m)"
        meta_license = "License Type (e.g., Public Domain, CC-BY)"
        meta_urls = {
            "home": "[https://provider.gov/data](https://provider.gov/data)",
            "docs": "[https://provider.gov/docs](https://provider.gov/docs)"
        }

        def __init__(self, **kwargs):
            super().__init__(name='mydata', **kwargs)
            # Initialize your specific headers or API endpoints here

        def run(self):
            # 1. Construct the download URL based on self.wgs_region
            # Note: APIs expect geographic coordinates! Use self.wgs_region
            # for web queries, and defer native self.region spatial logic to hooks.
            if self.wgs_region:
                api_bbox = f"{self.wgs_region.xmin},{self.wgs_region.ymin},{self.wgs_region.xmax},{self.wgs_region.ymax}"
            # 2. Use core.Fetch(url).fetch_req(...) to query the API for download urls
            # 3. Add successful download urls and attributes to the results with `self.add_entry_to_results'
            self.add_entry_to_results(
                url="https://my_fav_data_provider.org/data/data_file.zip",
                dst_fn="data_file.zip",
                data_type="zipped xyz data",
                agency="My Fav Data Provider!",
                date=2020,
                license="Public Domain",
            )
    ```
3. **Rebuild the module cache**
   Run `fetchez modules update-cache`

4.  **Test It:**
    Run `fetchez run mydata --help` to ensure it loads correctly.

## Handling Dependencies & Imports

Fetchez aims to keep its core footprint small. If your new module or plugin requires a non-standard library (e.g., `boto3`, `pyshp`, `netCDF4`):

1.  **Do Not Add to Core Requirements:** Do not add the library to the main `dependencies` list in `pyproject.toml`.
2.  **Add to Optional Dependencies:** Open `pyproject.toml` and add your library to a relevant group under `[project.optional-dependencies]`. If no group fits, create a new one (e.g. `netcdf = ["netCDF4"]`).
3.  **Soft Imports:** Wrap your imports in a `try/except ImportError` block so the module does not crash the CLI for users who don't use that specific data source.
4.  **Document It:** Clearly list the required packages (and the install command) in the class docstring.

	**Example:**

	```python
	# fetchez/modules/mys3.py
    from fetchez.core import FetchModule

	try:
        import boto3

        HAS_BOTO = True
    except ImportError:
        HAS_BOTO = False


    @cli.cli_opts(help_text="Fetch data from AWS")
    class MyS3Fetcher(FetchModule):
        """Fetches data from private S3 buckets.

        **Dependencies:**
        This module requires `boto3`.
        Install via: `pip install "fetchez[aws]"`
        Or:          `pip install boto3`
        """

        def run(self):
            if not HAS_BOTO:
                logger.error("Missing dependency 'boto3'. Please run: pip install 'fetchez[aws]'")
                return

            # Proceed with fetching...
	```
