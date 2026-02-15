# 🧪 Fetchez Workflows, Examples & Scripts

This directory contains standalone examples and scripts that demonstrate how to use `fetchez` as a Python library to build powerful geospatial workflows.

Unlike the core `fetchez` CLI, these scripts may require additional dependencies (like `gdal`, `pandas`, `rasterio`, or `geopandas`).

## 📂 Examples, Scripts, Etc.

| Script | Type | Description | Dependencies |
| :--- | :--- | :--- | :--- |
| `process_bing.py` | Script | Downloads Microsoft Building Footprints and merges them into a single GeoPackage. | `fetchez`, `gdal` |
| `visualize_tides.py` | Script | Fetches NOAA Tide data and generates a generic plot. | `fetchez`, `matplotlib`, `pandas` |
| `hook_reproject.py` | **Hook** | Automatically reprojects downloaded rasters using GDAL (e.g., `--hook reproject:crs=EPSG:3857`). | `fetchez`, `gdal` |
| `class2xyz.py` | **Hook (example)** | Extract LAS/LAZ points by classification and export ASCII XYZ (X Y Z). Output filename includes class tag(s) (e.g., `_c29.xyz`, `_c2-29-40.xyz`). *(No CRS transforms — use Globato for reprojection/gridding.)* | `fetchez`, `laspy` *(+ `lazrs` for `.laz`)* |

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

    # Reproject example hook
    cp hook_reproject.py ~/.fetchez/hooks/reproject.py

    # LAS/LAZ class → XYZ example hook
    cp class2xyz.py ~/.fetchez/hooks/class2xyz.py
    ```

2.  **Verify it Loaded:**
    ```bash
    fetchez --list-hooks
    # You should see 'reproject' and/or 'class2xyz' in the list.
    ```

3.  **Run it:**
    ```bash
    # Use the colon syntax for arguments: name:key=val,key2=val2

    # Example: reproject rasters
    fetchez copernicus --hook reproject:crs=EPSG:3857,suffix=_web

    # Example: extract ground points (class 2) to XYZ
    fetchez <module> ... --hook class2xyz:classes=2,out_dir=./ground_xyz

    # Example: extract bathy points (class 29) to XYZ (native CRS)
    fetchez dav -R -71.76/-71.70/41.32/41.36 --survey_id 8688 \
      --hook class2xyz:classes=29,out_dir=./bathy_xyz
    ```

    **Note (multiple classes):** Hook args are comma-delimited (`key=value,key=value,...`), so don’t use commas *inside* `classes=`.
    Use `+` (shell-safe) or quote `|`:
    ```bash
    # Shell-safe:
    --hook class2xyz:classes=2+29+40,out_dir=./classes_xyz

    # Pipe variant (must quote or escape):
    --hook "class2xyz:classes=2|29|40,out_dir=./classes_xyz"
    ```

## 🤝 How to Contribute

Have a cool script or a useful hook? We'd love to see it!

1.  The script should solve one specific problem well.
2.  The script should use `fetchez` in some way. (either importing the library or acting as a plugin)
3.  If you use external libraries outside of `fetchez` core, please list them at the top of your file.
4.  **Type:**
    * **Scripts:** Place in `examples/` (e.g., `make_map.py`).
    * **Hooks:** Place in `examples/` but mark them as hooks in the docstring (inherit from `fetchez.hooks.FetchHook`).
