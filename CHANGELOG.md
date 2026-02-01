# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
