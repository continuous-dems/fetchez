# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ADDED
- Add readable TNM elevation aliases while keeping the existing numeric selectors.
- Preserve TNM source metadata and allow `dedupe=false` to retain overlapping products.
- Add usgs_ds704 and usgs_of2005_1170 modules

### CHANGED
- Change the recipe batch_state output to live in `base_outdir` instead of `cwd`

### BUGFIX
- Skip the preview of a large Harmony job instead of abandoning it. Harmony answers a job over its preview threshold with the status `previewing`, which the poll did not recognise, so it stopped and the request came back empty; the job now has its preview skipped and is polled to completion.
- Keep download resume headers from leaking into other requests or caller-provided headers.
- Report a TNM API outage as an error instead of zero products, and never cache the results of a failed TNM query.
- Spatial cull corrects invalid geometries incorrectly read from shapefiles.
- Fix unzip hook checking for .tar.gz and .tgz compression.

## [0.8.5 - 2026-08-19]
### ADDED
- Sandbox (namespace) loaded external registry entries if they conflict with builtins.

### CHANGED
- Removed registry cache system

## [0.8.2 - 2026-08-09]
### CHANGED
- Update example scripts/etc.
- Allow readers.base to generate generic inf files
- local_fs module correctly parses Readers

### BUGFIX
- recipe.py would kill all fetching when one failed (even on ignore_failures).

## [0.8.1 - 2026-08-09]

### ADDED
- Use tags to search for recipes
- Add streams docs

### CHANGED
- Merged local_fs and path modules

### BUGFIX
- exclude_modules dict input fix

## [0.8.0 - 2026-08-06]
### ADDED
- Add new ModifierRegistry to intercept recipes and modify them before running
- Add `filelock` as dependency and include it's use in fetchez.core to prevent multiple processes from trying to fetch the same data.
- Add `filelock` to the copernicus_marine module (this uses a third-party library for fetching, so we wrap it in filelock).
- Add `cache` command cli to clear cache info
- Add `--refresh` option to refresh cache at runtime
- Add `--ignore-failures` option to ignore module and hook exceptions
- Add `Pipeline` and `read` functions to the api
- Add `BaseStream` class to fetchez.streams to yield chunks from `Readers`

### CHANGED
- Schemas are now for pure validation, mutations happen with modifiers instead
- Update recipe._generate_receipt to give some more useful information
- Update the use of paths in modules.base so that we use relative paths
- Update modules.base cached_run to use relative paths in cache instead of absolute paths
- Upgrade Exception handling for 'fail-fast' defaults
- Update most code to use pathlib, ongoing...
- Changed `--ignore-failures` to `--fail-fast` (may change back)
- Moved module/hook expansion from Recipe to registry

### BUGFIX
 - keyboard interrupt wouldn't correctly get passed to the concurrent threads and got looped into the logging library; moving the try/except to inside the with concurrent and adding a logging.debug in the keyboardinterrupt solves this and now is responsive and acting as expected.

## [0.7.0 - 2026-07-22]
### ADDED
- Refactor for better srs support
- Recipes translate command to output recipe as json
- New modules, including UHSLC, etc.
- Vector region support
- Recusrive bundle support
- Recipe 'translate' to dump a valid cli from a yaml
- Ensure `stream-init` gets set as the first hook in the `stream` stage.
- Add --region and --region-srs options to the `recipes run` cli
- Recursive preset support
- Added regions cli (from globato)

### CHANGED
- Modules must now use self.wgs_region to ensure valid wgs api requests, while self.region stays in original srs.
- Dropped fiona for pyogrio.
- Promoted pyogrio, shapely and pyproj to standard dependencies.
- Refresh readthedocs documentation.
- Refresh CLI documentation and help messages.
- Moved `yield_parsed_regions` from globato.utils to fetchez.spatial
- Refactor fetchez.recipe - moved a lot of stuff from globato, incl. batching, shared-cache

### BUGFIX
- fix to authentication in fetchez.core, now uses custom sessions
- enforce stream-init as first stream hook to run
- removed duplicate FetchModule from fetchez.core

## [0.6.4 - 2026-05-12]
### ADDED
- `stream` hook stage in core
- Moved compile_source function from globato.utils to utils

### CHANGED
- Updates gmrt module to use urls? endpoint for large regions

### BUGFIX
- typo in setsrs

## [0.6.3 - 2026-05-07]
### CHANGED
- Update gebco fetchez module to fetch new 2026 grid, and allow subsetting!
- Moved recipe validation from cli to fetchez.recipe
- Updated verbosity in fetchez.core


## [0.6.2 - 2026-04-30]
### ADDED
- ProfileRegistry - streams
- ReaderRegistry - streams
- copernicusmarine module (SDB)
- SYSU module (gravity based bathymetry)

### CHANGED
- Re-structure directories
-- 'macros' go in their parent directories
- Use click instead of argparse for CLI
- core.run_fetchez now returns the final list of entries for use in the api and elsewhere.
- Update run cli to allow for inherited options for modules.

### BUGFIX
- fix bug in earthdata.icesat2 for harmony fetching.

## [0.5.5 - 2026-04-24]
### ADDED
- BundleRegistry: bundle multiple modules + hooks in a yaml registry.

### CHANGED
- Update CDSE module to get B08 (IR)
- Change logging from name->module

## [0.5.5 - 2026-04-22]
### ADDED
- SYSU_topo dataset
- Add utility functions for dataset_id parsing

### CHANGED
- read_timeout in fetchez.core from None->120
- Descriptions in tqdm updated to be more useful
- Allow for POST in fetch_file

### BUGFIX
- fetchez_cache records empty results

## [0.5.4 - 2026-04-16]
### ADDED
- Added PresetRegistry into registry
- Add audit_full builtin preset
- Add GSHHG module (shorelines)
- Add CUSP module (shorelines (US))

### CHANGED
- Update recipe.py to use the new PresetRegistry
- Update nos_hydro for new API
- Update CLI for PresetRegistry
- Removed obsolete presets.py

## [0.5.3] - 2026-04-09
### ADDED
- Added parse_source_string and parse_hook_string in utils
- Added spatial.regions_intersect from cudem.regions

### CHANGED
- re-arranged cli help

### BUGFIX
- spatial region parsing of geojson files, returns all regions.

## [0.5.2] - 2026-04-02
### ADDED
- Add "lidarbc" fetchez modules (canada)
- Add .fetchez_cache to save module results for re-use
- Add RecipeRegistry to registry.py
- Add --list-recipes to cli

### CHANGED
- FetchModule is now in fetchez.modules
- fetchez.registry combines all registries (modules/hooks for now)
- Hooks are moved out of builtins to flat directory
- Now load extensions/plugins automatically
- Module metadata is prefixed with "meta_"
- Stage names: "pre" -> "manifest"; "post" -> "collection"
- Schema is now Schemas and uses global registry.
- Update to vdatum.geojson fred index of the vdatum module

### BUGFIX
- Update to fbt reading, accounting for heading; fix!

## [0.4.3] - 2026-03-02
- Breaks hooks into individual files, out of topical ones.
- Hooks are now auto-detected from 'builtins', so we don't have to maintain a registry.
- Adds 'focus' and 'datatype' builtin hooks.
- The 'unzip' hook now supports tar and gz.
- Post-hooks in fetchez.core was ignoring entry changes, this fixes that.
- We now use yaml files for config, including presets
- Fixed https (now url_fetcher) module bug.
- Add 'schemas' and 'recipe'.
- All builtin hooks in hooks.builtins.
- Add documentation.
- Some new modules.

## [0.4.2] - 2026-02-21
### Added
- Hook system for fetchez! (--list, --inventory, --pipe-path are now hooks)
- Users can add their own hooks in ~/.fetchez/hooks
- 'file' module to send local data through hooks
- --outdir option in CLI (global and per-module).
- Each entry now gets a 'history' key that keeps track of the hooks it passed through.

### Changed
- groupded parsers in argparse
- updated pyproject.toml for optional deps.

### BUGFIX
- pyproj/pyshp error msg in dav.py
- name conflict with cudem/coned/dav
- double path.join in core fixed. (this resulted in duplicated outdirs)
- unzip hook would send a bad entry record if the unzip files already existed

## [0.3.0] - 2026-02-01
### Added
- fetchez.spatial region_from_place centered on place
- Add TIGER
- Add arcticdem
- Add DAV
- fetchez.utils p_unzip from cudem.utils
- examples dir for examples, workflows, scripts using fetchez
- bing and tides examples
- sphinx auto-docs
- inventory option in the cli
- Most old fetches modules are now ported to fetchez

### Changed
- README updates
- CLI description (geospatial vs elevation)
- concurent.futures testing for threads
- STOP_EVENT in fetchez.core threads
- logger uses tqdm.write to not clobber progress bars
- spatial.parse_regions will now output all the regions found in a geojson

## [0.2.0] - 2026-01-27
### Added
- Initial standalone release of Fetchez.
- Decoupled from CUDEM project.
- New `fetchez.spatial` module for lightweight region parsing.
- New `fetchez.registry` for lazy module loading.
- Modernized CLI with logging support.
- FRED index now uses GeoJSON and Shapely directly (removed OGR dependency).
- csb module
- fetchez.spatial 'region_to_wkt' method
- fetchez.core fetch_req now supports 'method' arg
- fetchez.spatial 'region_center' method
- buouy module
- gmrt module
- fetchez.spatial 'region_to_bbox' method
- waterservices module
- etopo module
- fetchez.spatial 'region_to_geojson_geom'
- chs module
- bluetopo module
- user plugins
- add emodnet

### Changed
- Renamed project from `fetches` to `fetchez`.
- Refactored some old cudem.fetches modules to inherit from `fetchez	.core.FetchModule`.
- In fetchez.core, allow for transparent gzip (local size is larger than remote size)
