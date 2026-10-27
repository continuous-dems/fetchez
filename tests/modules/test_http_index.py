"""Offline contract tests for the generic HTTPIndex module.

These use small FetchModule/FRED stand-ins; run full repository tests as well.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def setup_module(monkeypatch):
    pkg = types.ModuleType("fetchez")
    pkg.__path__ = []
    cli = types.ModuleType("fetchez.cli")
    cli.cli_opts = lambda **kwargs: lambda cls: cls
    modules = types.ModuleType("fetchez.modules")
    spatial = types.ModuleType("fetchez.spatial")
    core = types.ModuleType("fetchez.core")
    fred = types.ModuleType("fetchez.fred")
    pages = {}
    hits = []

    class Region:
        def __init__(self, w=None, e=None, s=None, n=None, srs=None):
            self.w, self.e, self.s, self.n, self.srs = w, e, s, n, srs

        def valid_p(self):
            return self.w is not None and self.w < self.e and self.s < self.n

        def to_geojson_geometry(self):
            return {
                "type": "Polygon",
                "coordinates": [
                    [
                        [self.w, self.s],
                        [self.e, self.s],
                        [self.e, self.n],
                        [self.w, self.n],
                        [self.w, self.s],
                    ]
                ],
            }

        def to_shapely(self):
            return self

        def intersects(self, other):
            return (
                self.w <= other.e
                and self.e >= other.w
                and self.s <= other.n
                and self.n >= other.s
            )

    class FetchModule:
        def __init__(self, region=None, **kwargs):
            self._init_kwargs = {"region": region}
            self.wgs_region = region or Region(-180, 180, -90, 90, srs="EPSG:4326")
            self.results = []
            self.status = 0

        def add_entry_to_results(self, url, dst_fn, data_type, metadata=None):
            self.results.append(
                {
                    "url": url,
                    "dst_fn": dst_fn,
                    "data_type": data_type,
                    "metadata": metadata,
                }
            )

    class Page:
        def __init__(self, urls):
            self.urls = urls

        def xpath(self, expr):
            return self.urls

    class Fetch:
        def __init__(self, url):
            self.url = url

        def fetch_html(self):
            hits.append(self.url)
            return Page(pages[self.url]) if self.url in pages else None

    class FRED:
        storage = {}

        def __init__(self, name, path=None):
            self.name = name
            self.filename = f"{name}.geojson"
            self.path = Path(path or self.filename)
            self.features = list(self.storage.get(name, []))

        def save(self):
            self.storage[self.name] = list(self.features)

        def search(self, region=None):
            for feat in self.features:
                coords = feat["geometry"]["coordinates"][0]
                b = Region(
                    min(x for x, y in coords),
                    max(x for x, y in coords),
                    min(y for x, y in coords),
                    max(y for x, y in coords),
                )
                if region is None or b.intersects(region):
                    yield feat["properties"]

    spatial.Region = Region
    modules.FetchModule = FetchModule
    core.Fetch = Fetch
    fred.FRED = FRED
    pkg.core = core
    pkg.fred = fred
    for key, value in {
        "fetchez": pkg,
        "fetchez.cli": cli,
        "fetchez.modules": modules,
        "fetchez.spatial": spatial,
        "fetchez.core": core,
        "fetchez.fred": fred,
    }.items():
        monkeypatch.setitem(sys.modules, key, value)
    spec = importlib.util.find_spec("fetchez.modules.http_index")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, pages, hits, Region, FRED


def test_direct_crawl_no_region(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/project/"] = ["survey.zip", "profile.txt", "docs.html"]
    obj = mod.HTTPIndex(url="https://example.org/project/", pattern=["*.zip", "*.txt"])
    obj.run()
    assert {entry["dst_fn"] for entry in obj.results} == {"survey.zip", "profile.txt"}
    assert hits == ["https://example.org/project/"]


def test_direct_crawl_explicit_region_without_footprints_does_not_filter(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/project/"] = ["a.zip", "b.zip"]
    obj = mod.HTTPIndex(
        url="https://example.org/project/",
        pattern="*.zip",
        region=Region(-120, -119, 33, 34),
    )
    obj.run()
    assert len(obj.results) == 2


def test_static_footprint_filters_only_with_explicit_region(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/project/"] = ["a.zip"]
    kwargs = dict(
        url="https://example.org/project/",
        pattern="*.zip",
        footprint={"method": "static", "bounds": [-120, -119, 33, 34]},
    )
    assert len(mod.HTTPIndex(**kwargs).run().results) == 1
    assert len(mod.HTTPIndex(**kwargs, region=Region(0, 1, 0, 1)).run().results) == 0
    assert (
        len(
            mod.HTTPIndex(**kwargs, region=Region(0, 1, 0, 1), filter_region=False)
            .run()
            .results
        )
        == 1
    )


def test_index_is_built_and_reused_without_crawling(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/tiles/"] = ["tile_10_20.tif", "tile_30_40.tif"]
    kwargs = dict(
        url="https://example.org/tiles/",
        pattern="*.tif",
        index=True,
        index_name="tiles",
        footprint={
            "method": "filename",
            "regex": r"tile_(?P<x>\d+)_(?P<y>\d+)\.tif",
            "width": 2,
            "height": 2,
        },
    )
    obj = mod.HTTPIndex(**kwargs).run()
    assert len(obj.results) == 2
    assert len(FRED.storage["tiles"]) == 2
    hits.clear()
    obj = mod.HTTPIndex(**kwargs, region=Region(10, 11, 20, 21)).run()
    assert len(obj.results) == 1
    assert hits == []


def test_recursion_is_opt_in_and_bounded(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/start/"] = [
        "sub/",
        "file.zip",
        "https://outsider.org/data.zip",
    ]
    pages["https://example.org/start/sub/"] = ["nested.zip", "../"]
    obj = mod.HTTPIndex(url="https://example.org/start/", pattern="*.zip").run()
    assert len(obj.results) == 1
    obj = mod.HTTPIndex(
        url="https://example.org/start/",
        pattern="*.zip",
        recursive=True,
        follow_pattern="*/",
        max_depth=1,
    ).run()
    assert len(obj.results) == 2


def test_missing_footprints_do_not_publish_empty_index(setup_module):
    mod, pages, hits, Region, FRED = setup_module
    pages["https://example.org/tiles/"] = ["unmatched.tif"]
    obj = mod.HTTPIndex(
        url="https://example.org/tiles/",
        pattern="*.tif",
        index=True,
        index_name="missing",
        footprint={
            "method": "filename",
            "regex": r"tile_(?P<x>\d+)_(?P<y>\d+)\.tif",
            "width": 2,
            "height": 2,
        },
    ).run()
    assert obj._discovery_failed
    assert "missing" not in FRED.storage
