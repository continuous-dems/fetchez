<!-- DRAFT for continuous-dems/fetchez. Suggested title:
     TNM: outage detection and S3-based modules
-->

## Summary

The TNM REST API (`tnmaccess.nationalmap.gov`) was down from about 12:40 MT on 2026-09-16 until about 11:15 MT on 2026-09-17. During that time the `tnm` module read the outage as "no products here", logged nothing, and cached the empty answer, so builds finished without any 3DEP/NED data and gave no sign of it.

After some discussion with @matth-love and @camante, this issue proposes two changes:

1. **A small fix to `tnm`** so an API outage is reported as an `[ ERROR ]` and is never cached.
2. **New dataset-specific modules in a `tnm_s3.py`** that find USGS elevation products directly in the public `prd-tnm` S3 bucket, without the REST API. Recipes could then use these for the datasets they cover, and `tnm` stays available for everything else.

Nothing here changes what `tnm` does while the API is working.

## Background

During the outage the API answered HTTP 200 with this body:

```json
{"error": "Expecting value: line 1 column 1 (char 0)", "showToast": true, "toastMessage": "...", "toastType": "warning"}
```

`tnm` checks for `{errorMessage…}` but not for this shape. In the default (non-strict) mode, `data.get("total", 0)` and `data.get("items", [])` turn the body into an empty result, and `FetchModule._cached_run` then writes `[]` to `.fetchez_cache`. From then on the empty answer is replayed from the cache, even after the API recovers. (`strict_datasets=True` already raises on this body; the default mode does not.)

The data itself was never unavailable. The files and a public bucket listing were reachable on `prd-tnm.s3.amazonaws.com` the whole time.

## Part 1: `tnm` reports an outage (small PR)

Treat all of these as "the API gave no usable answer", in strict and non-strict mode alike: no response, a non-200 status, an `{errorMessage…}` body, a non-JSON body, or a JSON body that has an `error` key or lacks `total` / `items`.

| Situation | What `tnm` does | Log | Cached? |
|---|---|---|---|
| API working, including a genuine "no products" answer | Same as today | Nothing new | Yes, as today |
| API gave no usable answer, default mode | Returns no products | `[ ERROR ] tnm: TNM API unavailable (<reason>). No products returned; this result is not cached.` | **No** |
| Same, with `strict_datasets` or `products=` | Raises, as strict mode does today | Same `[ ERROR ]` | **No** |
| API fails part-way through pagination | The partial list is dropped, then as above | Same `[ ERROR ]` | **No** |

This needs one small change outside `tnm.py`: `FetchModule._cached_run` skips writing the cache file when a module flags that its discovery failed (a private attribute, so cache keys are unaffected). Without that, the error would be logged once and the empty result replayed silently afterwards. The new modules in Part 2 would use the same flag.

## Part 2: S3-based modules (`tnm_s3.py`)

One file with a shared base class and a thin subclass per dataset, the way `tnm.py` already holds `tnm`, `ned` and `3dep`. Each dataset gets its own module name, so a recipe says exactly which product it wants and attaches hooks and weights to a known file type.

| Module | Dataset | How products are found | Status |
|---|---|---|---|
| `tnm_1as` | NED 1 arc-second | 1° cells from the region, then the S3 listing of `StagedProducts/Elevation/1/TIFF/historical/<cell>/` | Prototyped and compared with the API (below) |
| `tnm_13as` | NED 1/3 arc-second | Same, under `Elevation/13/` | Prototyped and compared with the API |
| `tnm_1m` | DEM 1 meter (project-based) | Project outlines from `FESM_1m.gpkg`, then the S3 listing of each project's `TIFF/` folder; tile footprints from the file names | Prototyped; more checking needed (below) |
| `tnm_s1m` | Seamless 1 m DEM (S1M) | `S1M_Products.gpkg` | Not started |
| `tnm_19as` | NED 1/9 arc-second | `FESM_19.shp` | Not started |
| `tnm_2as_ak` | NED Alaska 2 arc-second (Alaska only) | `FESM_2.gpkg` and the other `.gpkg` files beside it | Not started |
| `tnm_5m_ifsar` | Alaska IFSAR 5 m DEM (Alaska only, IFSAR-derived) | Index still to be identified (staged under `OPR/Projects/`) | Not started |
| `tnm_opr` | Original Product Resolution DEMs | `OPR_TESM.gpkg` | Not started |
| `tnm_lpc` | Lidar point clouds | `LPC_TESM.gpkg` | Not started |
| `tnm_dsm` | IFSAR DSM | `FESM_DSM_Proj.gpkg`, `FESM_DSM_Tile.gpkg` | Not started |

The names follow the product aliases already in `tnm.py` (`1_as`, `1_3as`, `1_9as`, `1m`, `s1m`), kept short. The two Alaska products carry a suffix so nobody reads `2as` as a coarser copy of `1as` with the same coverage, or `5m` as a resampled `1m`: the 2 arc-second tiles exist only for Alaska, and the 5 m DEMs come from IFSAR rather than lidar. Suggestions welcome.

### Proposed behaviour

- **No REST API calls at all.** Only the S3 bucket listing and, where a dataset needs one, the USGS index file staged in the same bucket (table at the end). The ArcGIS 3DEP Elevation Index is not used (see below).
- **One policy for every index file**, in this order:
  1. a local copy in the cache, if there is one **and** it is still the latest version (its size and modification time match the S3 listing);
  2. otherwise, read the file remotely with a bounding box (`/vsicurl/`), which needs no download;
  3. otherwise, download it into the cache once, and read it locally.

  Where a dataset has several index files (Alaska 2 arc-second, IFSAR DSM), all of them are read the same way and the results are combined, with duplicates removed by download URL.
- **Same cache folder and file names as `tnm`.** The modules write into `<outdir>/tnm/` (as `ned` already does) and keep the dated names the API uses, e.g. `USGS_13_n36w121_20250826.tif`. Existing caches are reused as they are, and using `tnm` and `tnm_13as` against the same cache never stores a file twice.
- **NED: newest version only, by default.** Each cell has several dated versions under `historical/`. The module returns the newest one per cell, so no `spatial_cull` step is needed just to pick a version, and the file name still records which version was used. A way to ask for older versions can come later.
- **An empty listing is a real answer** (an ocean cell has nothing staged) and is cached like any other result.
- **A failed discovery is never read as "no data".** If the list of files cannot be obtained (S3 unreachable, a non-200 status, malformed XML, a truncated listing, or an index file that cannot be read by any of the three routes above), the module logs an `[ ERROR ]`, returns no products, and caches nothing. With `strict=True` the same failure is raised as an exception instead of being left to the pipeline.
- **Entries look like `tnm` entries**: `url`, `dst_fn`, `data_type="tnm"`, `format`, `bounds`, `geometry`, `date`, `remote_size`, `title`, `tnm_product`, `tnm_dataset`, and `tnm_project` for 1 m, so existing hooks keep working.
- **No new dependencies.** `lxml`, `shapely`, `pyproj`, `pyogrio` and `filelock` are already core dependencies.

### What has been checked so far

NED 1 and 1/3 arc-second, S3 listing against the live API in 8 regions (California, Texas, Montana, Virginia, Puerto Rico, open ocean):

- Identical URL lists and file names in every region, with one exception: the API lists `USGS_1_n38w123_20210409.tif`, which no longer exists in the bucket.
- The API never returns the undated file under `current/`; it is the same file as the newest dated one under `historical/`.
- The API's `sizeInBytes` is often wrong (47,795 against an actual 48,945,340 for one file). The S3 listing size is exact.
- A CRM tile built from the S3-discovered list used the same cached files a normal run would have.

1 m, FESM + S3 listing against the live API in 9 regions:

- Tile file names come in three styles: `USGS_1M_<zone>_x<E>y<N>_…`, `USGS_one_meter_x<E>y<N>_…` and `USGS_1m_x<E>y<N>_…`. In all three, x/y are the tile's north-west corner in units of 10 km, in NAD83 UTM, with a 6 m collar (checked against real file headers). Roughly 70% of projects use a style with no zone in the name, and a project can extend one zone's grid past the 6° line (western Puerto Rico is gridded in zone 20), so the zone has to be worked out from the query region.
- In 7 of the 9 regions the URL lists matched the API exactly. In one of the other two, the API left out a tile that overlaps the query box by about 100 m (it also returns tiles that sit about 30 m outside the box, so its edge test is not exactly reproducible). In the other, the API returned two tiles whose rectangles reach about 2 km into the box but whose project outline does not, so the project lookup missed them; looking projects up with a one-tile margin around the box should cover that, but it has not been re-checked yet.
- `FESM_1m.gpkg` can be queried by bounding box straight from S3 (`/vsicurl/`), without downloading the 1.9 GB file; that took 2 to 11 s per query.
- The ArcGIS 3DEP Elevation Index was also tried as the project index and is not proposed: its "1 Meter" layer has 13 outlines with empty links (Puerto Rico, Hawaii) and did not yet link a project that FESM dates two days earlier. FESM listed every project folder the API returned in all 9 regions.
- FESM's publication dates differ between overlapping projects, while the API gives many projects the same date (`2020-03-30`), so a date-based `spatial_cull` can pick a different project than it does with API results.

### Open questions

- **Is FESM complete?** It lists 931 project folders and the bucket has 966. At least one of the extra folders has no `TIFF/` folder, so some may be empty or retired, but this needs checking against the API before `tnm_1m` is relied on. FESM is in USGS's own bucket and is rewritten every few days, but I could not find USGS documentation for it (the "3DEP Spatial Metadata" page covers WESM only), so its schema may change. If the expected layer or fields are missing, the module should report an error rather than guess.
- **The other index files have not been opened yet.** Each one needs the same check `FESM_1m.gpkg` got (what it lists, whether it links to files or to folders, and whether it agrees with the API) before its module is written. Several are old (`FESM_19.shp` is from 2018, `FESM_2.gpkg` from 2021), which may be fine for datasets that are no longer updated.
- **Large index files.** `OPR_TESM.gpkg` is 12.2 GB and `LPC_TESM.gpkg` 3.1 GB, so for those the remote bounding-box read matters most. When the download step is reached it should log a `[ WARNING ]` with the size and carry on, not ask for confirmation: these jobs usually run unattended from scripts, often overnight, and a prompt in the middle of a run would stall them.
- **Cached discovery answers** are kept indefinitely (as for every module), so "newest version" means newest as of the first run in a given cache. That is the same as `tnm` today; noting it rather than proposing a change.

### Index files for the remaining datasets

All under `StagedProducts/Elevation/` in the `prd-tnm` bucket. Only `FESM_1m.gpkg` has been opened so far; the rest are listed by name, size and date.

| Module | Product | Index file | Size | Last updated |
|---|---|---|---|---|
| `tnm_1as`, `tnm_13as` | NED 1 and 1/3 arc-second | none needed (fixed 1° grid + S3 listing) | | |
| `tnm_1m` | 1 m DEM (project-based) | `1m/FullExtentSpatialMetadata/FESM_1m.gpkg` | 1.9 GB | 2026-09-17 |
| | 1 m tile grid (reference only) | `1m/FullExtentSpatialMetadata/10_km_cell_grid.gpkg` | 51 MB | 2026-02-12 |
| `tnm_s1m` | Seamless 1 m (S1M) | `S1M/FullExtentSpatialMetadata/S1M_Products.gpkg` | 18 MB | 2026-09-17 |
| `tnm_19as` | NED 1/9 arc-second | `19/FullExtentSpatialMetadata/FESM_19.shp` | 295 MB | 2018-06-28 |
| `tnm_2as_ak` | Alaska 2 arc-second | `2/FullExtentSpatialMetadata/FESM_2.gpkg` (plus several `fe####.gpkg`) | 22 MB | 2021-07-29 |
| `tnm_5m_ifsar` | Alaska IFSAR 5 m | not identified yet | | |
| `tnm_opr` | OPR DEMs | `OPR/FullExtentSpatialMetadata/OPR_TESM.gpkg` | 12.2 GB | 2026-09-11 |
| `tnm_lpc` | Lidar point clouds (LPC) | `LPC/FullExtentSpatialMetadata/LPC_TESM.gpkg` | 3.1 GB | 2026-09-17 |
| `tnm_dsm` | IFSAR DSM | `FullExtentSpatialMetadata/FESM_DSM_Proj.gpkg`, `FESM_DSM_Tile.gpkg` | 20 MB, 1.6 MB | 2022-05-24 |

## Suggested order

1. PR: `tnm` outage detection + the no-cache rule in `FetchModule._cached_run`, with tests.
2. PR: `tnm_s3.py` with `tnm_1as` and `tnm_13as`, with tests that compare against recorded API answers.
3. PR: `tnm_1m`, after the FESM completeness check and a wider comparison with the API.
4. Later, one dataset at a time: S1M, 1/9 arc-second, Alaska, OPR, LPC.
5. Separately, in globato: switch the bundles that use `module: tnm` for NED over to the new modules, once (2) is merged and a tile built both ways has been compared.

@camante, this may also be a useful base for the `glob-tnm` hierarchy work, since it would not depend on the REST API being up. Part 1 touches only the failure handling inside the query loop in `tnm.py`, so it should be a small rebase for `feat/tnm-elevation-provider`.
