# 🧪 Fetchez Workflows, Examples & Scripts

This directory contains standalone examples and scripts that demonstrate how to use `fetchez` as a Python library to build powerful geospatial workflows.

Unlike the core `fetchez` CLI, these scripts may require additional dependencies (like `gdal`, `pandas`, `rasterio`, or `geopandas`).

## 📂 Examples, Scripts, Etc.

| Script | Type | Description | Dependencies |
| :--- | :--- | :--- | :--- |
| `process_bing.py` | Script | Downloads Microsoft Building Footprints and merges them into a single GeoPackage. | `fetchez`, `gdal` |
| `visualize_tides.py` | Script | Fetches NOAA Tide data and generates a generic plot. | `fetchez`, `matplotlib`, `pandas` |
| `hook_reproject.py` | **Hook** | Automatically reprojects downloaded rasters using GDAL (e.g., `--hook reproject:crs=EPSG:3857`). | `fetchez`, `gdal` |

## 💻 How to Run

### 1. Standalone Scripts
These are standard Python scripts that import `fetchez` as a library.

1.  Ensure you have `fetchez` installed (`pip install fetchez`).
2.  Install any script-specific dependencies (e.g., `conda install gdal`).
3.  Run the script directly:
    ```bash
    python process_bing.py -R -105.5/-104.5/39.5/40.5 -o my_data.gpkg
    ```

### 2. User Hooks
Hooks are plugins that `fetchez` loads automatically. To use an example hook:

1.  **Install the Hook:** Copy the file to your local configuration directory.
    ```bash
    mkdir -p ~/.fetchez/hooks/
    cp hook_reproject.py ~/.fetchez/hooks/reproject.py
    ```
2.  **Verify it Loaded:**
    ```bash
    fetchez --list-hooks
    # You should see 'reproject' in the list.
    ```
3.  **Run it:**
    ```bash
    # Use the colon syntax for arguments: name:key=val,key2=val2
    fetchez copernicus --hook reproject:crs=EPSG:3857,suffix=_web
    ```

## 🤝 How to Contribute

Have a cool script or a useful hook? We'd love to see it!

1.  The script should solve one specific problem well.
2.  The script should use `fetchez` in some way. (either importing the library or acting as a plugin)
3.  If you use external libraries outside of `fetchez` core, please list them at the top of your file.
4.  **Type:**
    * **Scripts:** Place in `examples/` (e.g., `make_map.py`).
    * **Hooks:** Place in `examples/` but mark them as hooks in the docstring (inherit from `fetchez.hooks.FetchHook`).