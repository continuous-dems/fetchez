"""Contract tests for the supplied generic REST module."""

import importlib.util
import json
import sys
import types
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.error import URLError

import pytest


@pytest.fixture
def rest_module(monkeypatch, tmp_path):
    """Isolated contract test: mirrors the FetchModule entry interface."""
    fetchez = types.ModuleType("fetchez")
    fetchez.__path__ = []
    modules = types.ModuleType("fetchez.modules")
    cli = types.ModuleType("fetchez.cli")
    cli.cli_opts = lambda **kwargs: lambda cls: cls

    class Region:
        def __init__(self, w=-120, e=-119, s=32, n=33, srs="EPSG:4326"):
            self.w, self.e, self.s, self.n, self.srs = w, e, s, n, srs

        def copy(self):
            return Region(self.w, self.e, self.s, self.n, self.srs)

        def valid_p(self):
            return self.w < self.e and self.s < self.n

        def warp(self, target):
            self.srs = target
            return self

        def format(self, style):
            if style == "bbox":
                return f"{self.w},{self.s},{self.e},{self.n}"
            if style == "wkt":
                return "POLYGON ((-120 32, -120 33, -119 33, -119 32, -120 32))"
            if style == "geojson":
                return json.dumps(self.to_geojson_geometry())
            if style == "arcgis":
                return json.dumps(self.to_arcgis_envelope())
            if style in {"region", "bbox_wesn"}:
                return f"{self.w},{self.e},{self.s},{self.n}"
            raise ValueError(style)

        def to_bbox(self):
            return self.w, self.s, self.e, self.n

        def to_list(self):
            return [self.w, self.e, self.s, self.n]

        def to_geojson_geometry(self):
            return {
                "type": "Polygon",
                "coordinates": [
                    [
                        [self.w, self.s],
                        [self.w, self.n],
                        [self.e, self.n],
                        [self.e, self.s],
                        [self.w, self.s],
                    ]
                ],
            }

        def to_arcgis_envelope(self):
            return {
                "xmin": self.w,
                "ymin": self.s,
                "xmax": self.e,
                "ymax": self.n,
                "spatialReference": {"wkid": 4326},
            }

    class FetchModule:
        def __init__(self, src_region=None, **kwargs):
            self.region = src_region or Region()
            self._init_kwargs = {"region": src_region}
            self.results = []
            self.headers = {}
            self._outdir = str(tmp_path)
            self._discovery_failed = False
            self.status = 0
            self.wgs_region = self.region.copy()

        def add_entry_to_results(self, url, dst_fn, data_type, **kwargs):
            self.results.append(
                {"url": url, "dst_fn": str(dst_fn), "data_type": data_type, **kwargs}
            )

    modules.FetchModule = FetchModule
    monkeypatch.setitem(sys.modules, "fetchez", fetchez)
    monkeypatch.setitem(sys.modules, "fetchez.modules", modules)
    monkeypatch.setitem(sys.modules, "fetchez.cli", cli)
    here = Path(__file__).resolve()
    candidates = [
        here.with_name("rest.py"),
        *[
            parent / "src" / "fetchez" / "modules" / "rest.py"
            for parent in here.parents
        ],
        *[parent / "fetchez" / "modules" / "rest.py" for parent in here.parents],
    ]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("Could not locate fetchez/modules/rest.py")
    spec = importlib.util.spec_from_file_location("rest_test_target", path)
    target = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(target)
    return target, Region


class Response:
    def __init__(self, payload, url):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def geturl(self):
        return self.url


def test_json_discovery_and_metadata(rest_module, monkeypatch):
    target, _ = rest_module
    observed = []

    def fake_open(request, timeout):
        observed.append(request)
        return Response(
            {
                "data": {
                    "items": [
                        {
                            "id": "s1",
                            "file": {"href": "/files/tile.tif", "name": "tile.tif"},
                            "props": {"title": "Survey"},
                        }
                    ]
                }
            },
            request.full_url,
        )

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/api",
        mode="discover",
        results_path="data.items",
        url_field="file.href",
        filename_field="file.name",
        id_field="id",
        metadata_fields={"title": "props.title"},
    )
    assert mod.run() is mod
    assert len(mod.results) == 1
    entry = mod.results[0]
    assert entry["url"] == "https://test.example/files/tile.tif"
    assert entry["dst_fn"].startswith("tile_") and entry["dst_fn"].endswith(".tif")
    assert entry["metadata"] == {"title": "Survey", "source_id": "s1"}
    assert len(observed) == 1


def test_bbox_interpolation_and_repeated_params(rest_module, monkeypatch):
    target, Region = rest_module
    mod = target.RestAPIModule(
        url="https://test.example/search",
        src_region=Region(),
        parameters=[
            ["filter", "active"],
            ["filter", "spatialQuery={region:wkt}"],
            ["bbox", "{region:bbox}"],
        ],
    )
    q = parse_qs(urlsplit(mod.build_url()).query)
    assert q["bbox"] == ["-120,32,-119,33"]
    assert len(q["filter"]) == 2
    assert "POLYGON" in q["filter"][1]


def test_body_native_geojson(rest_module):
    target, Region = rest_module
    mod = target.RestAPIModule(
        url="https://test.example/search",
        src_region=Region(),
        method="POST",
        body={"geometry": "{region:geojson}"},
    )
    body = mod._expand(mod.body)
    assert isinstance(body["geometry"], dict)
    assert body["geometry"]["type"] == "Polygon"


def test_region_placeholder_requires_explicit_region(rest_module):
    target, _ = rest_module
    mod = target.RestAPIModule(
        url="https://test.example/search", parameters={"bbox": "{region:bbox}"}
    )
    assert mod.run() is mod
    assert mod._discovery_failed is True
    assert mod.results == []


def test_next_link_pagination_and_limit(rest_module, monkeypatch):
    target, _ = rest_module
    requests = []

    def fake_open(request, timeout):
        requests.append(request.full_url)
        if len(requests) == 1:
            data = {
                "results": [{"url": "https://test.example/1.tif"}],
                "next": "?page=2",
            }
        else:
            data = {"results": [{"url": "https://test.example/2.tif"}], "next": None}
        return Response(data, request.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        results_path="results",
        url_field="url",
        pagination={"type": "next", "path": "next"},
    )
    mod.run()
    assert [entry["url"] for entry in mod.results] == [
        "https://test.example/1.tif",
        "https://test.example/2.tif",
    ]
    assert len(requests) == 2


def test_offset_pagination(rest_module, monkeypatch):
    target, _ = rest_module
    offsets = []

    def fake_open(request, timeout):
        offset = int(parse_qs(urlsplit(request.full_url).query).get("offset", [0])[0])
        offsets.append(offset)
        return Response(
            {
                "data": [{"url": f"https://test.example/{offset}.tif"}]
                if offset < 2
                else []
            },
            request.full_url,
        )

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        results_path="data",
        url_field="url",
        pagination={"type": "offset", "page_size": 1},
    )
    mod.run()
    assert offsets == [0, 1, 2]
    assert len(mod.results) == 2


def test_response_get_registers_remote_entry(rest_module):
    target, _ = rest_module
    mod = target.RestAPIModule(url="https://test.example/api", parameters={"a": 1})
    mod.run()
    assert mod.results[0]["url"] == "https://test.example/api?a=1"
    assert mod.results[0]["dst_fn"].endswith(".json")
    assert mod._discovery_failed is False


def test_post_response_materialized(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(request, timeout):
        assert request.get_method() == "POST"
        assert json.loads(request.data)["x"] == 5
        return Response({"ok": True}, request.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/api", method="POST", body={"x": 5}
    )
    mod.run()
    assert mod.results[0]["status"] == 0
    assert Path(mod.results[0]["dst_fn"]).exists()


def test_bad_json_is_not_cached_as_empty(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(request, timeout):
        class Raw(Response):
            def read(self):
                return b"not-json"

        return Raw(None, request.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/api",
        mode="discover",
        results_path="results",
        url_field="url",
    )
    mod.run()
    assert mod._discovery_failed
    assert not mod.results


def test_detail_follows_sciencebase_items_and_expands_all_files(
    rest_module, monkeypatch
):
    target, _ = rest_module
    requested = []

    def fake_open(request, timeout):
        requested.append(request.full_url)
        if "/catalog/items" in request.full_url:
            data = {
                "items": [
                    {
                        "id": "item1",
                        "title": "Bathymetry survey",
                        "link": {
                            "url": "https://www.sciencebase.gov/catalog/item/item1"
                        },
                    },
                    {
                        "id": "item2",
                        "title": "No attachments",
                        "link": {
                            "url": "https://www.sciencebase.gov/catalog/item/item2"
                        },
                    },
                ]
            }
        elif "/item/item1" in request.full_url:
            data = {
                "files": [
                    {
                        "name": "one.tif",
                        "url": "https://www.sciencebase.gov/catalog/file/get/one",
                        "size": 99,
                    },
                    {
                        "name": "two.zip",
                        "url": "https://www.sciencebase.gov/catalog/file/get/two",
                        "size": 120,
                    },
                ]
            }
        else:
            data = {"files": []}
        return Response(data, request.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://www.sciencebase.gov/catalog/items",
        mode="discover",
        results_path="items",
        id_field="id",
        metadata_fields={"title": "title"},
        detail={
            "url_field": "link.url",
            "parameters": {"format": "json"},
            "results_path": "files",
            "asset_url_field": "url",
            "filename_field": "name",
            "metadata_fields": {"size": "size"},
        },
    )
    mod.run()
    assert not mod._discovery_failed
    assert len(mod.results) == 2
    assert {e["url"] for e in mod.results} == {
        "https://www.sciencebase.gov/catalog/file/get/one",
        "https://www.sciencebase.gov/catalog/file/get/two",
    }
    assert all(e["metadata"]["title"] == "Bathymetry survey" for e in mod.results)
    assert all(e["metadata"]["source_id"] == "item1" for e in mod.results)
    assert sorted(e["metadata"]["size"] for e in mod.results) == [99, 120]
    assert len(requested) == 3
    assert "format=json" in requested[1]


def test_detail_rejects_cross_host_by_default(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(request, timeout):
        return Response(
            {"items": [{"link": {"url": "https://other.example/item/1"}}]},
            request.full_url,
        )

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://source.example/items",
        mode="discover",
        results_path="items",
        detail={"url_field": "link.url", "asset_url_field": "url"},
    )
    mod.run()
    assert mod._discovery_failed and not mod.results


def test_repeated_parameters_from_list(rest_module):
    target, Region = rest_module
    mod = target.RestAPIModule(
        url="https://test.example/catalog",
        src_region=Region(),
        parameters=[["filter", "public"], ["filter", "spatialQuery={region:wkt}"]],
    )
    query = parse_qs(urlsplit(mod.build_url()).query)
    assert query["filter"][0] == "public"
    assert "POLYGON" in query["filter"][1]


def test_duplicate_urls_are_registered_once(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(request, timeout):
        return Response(
            {
                "records": [
                    {"url": "/asset.tif"},
                    {"url": "/asset.tif"},
                ]
            },
            request.full_url,
        )

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/items",
        mode="discover",
        results_path="records",
        url_field="url",
    )
    mod.run()
    assert len(mod.results) == 1
    assert not mod._discovery_failed


def test_successful_empty_discovery_is_not_a_failure(rest_module, monkeypatch):
    target, _ = rest_module
    monkeypatch.setattr(
        target, "urlopen", lambda req, timeout: Response({"items": []}, req.full_url)
    )
    mod = target.RestAPIModule(
        url="https://test.example/items",
        mode="discover",
        results_path="items",
        url_field="url",
    )
    mod.run()
    assert mod.results == []
    assert mod._discovery_failed is False


def test_detail_metadata_and_limit(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(req, timeout):
        if req.full_url.endswith("/search"):
            return Response(
                {"items": [{"id": "a", "title": "Survey", "link": {"url": "/item/a"}}]},
                req.full_url,
            )
        return Response(
            {
                "files": [
                    {"url": "/one.tif", "name": "one.tif", "size": 2},
                    {"url": "/two.tif", "name": "two.tif", "size": 3},
                ]
            },
            req.full_url,
        )

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        results_path="items",
        id_field="id",
        metadata_fields={"title": "title"},
        limit=1,
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
            "filename_field": "name",
            "metadata_fields": {"bytes": "size"},
        },
    )
    mod.run()
    assert len(mod.results) == 1
    assert mod.results[0]["metadata"] == {
        "title": "Survey",
        "source_id": "a",
        "bytes": 2,
    }


def test_detail_failure_must_invalidate_discovery_cache(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(req, timeout):
        if req.full_url.endswith("/search"):
            return Response({"items": [{"link": {"url": "/item/1"}}]}, req.full_url)
        raise URLError("temporary outage")

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        results_path="items",
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
        },
    )
    mod.run()
    assert mod._discovery_failed is True


def test_post_search_uses_get_for_detail(rest_module, monkeypatch):
    target, _ = rest_module
    methods = []

    def fake_open(req, timeout):
        methods.append(req.get_method())
        if len(methods) == 1:
            return Response({"items": [{"link": {"url": "/item/1"}}]}, req.full_url)
        return Response({"files": [{"url": "/file.tif"}]}, req.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        method="POST",
        body={"query": "all"},
        mode="discover",
        results_path="items",
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
        },
    )
    mod.run()
    assert methods == ["POST", "GET"]


def test_detail_parameters_interpolate_region(rest_module, monkeypatch):
    target, Region = rest_module
    requests = []

    def fake_open(req, timeout):
        requests.append(req.full_url)
        if len(requests) == 1:
            return Response({"items": [{"link": {"url": "/item/1"}}]}, req.full_url)
        return Response({"files": [{"url": "/file.tif"}]}, req.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        src_region=Region(),
        results_path="items",
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
            "parameters": {"bbox": "{region:bbox}"},
        },
    )
    mod.run()
    assert parse_qs(urlsplit(requests[1]).query)["bbox"] == ["-120,32,-119,33"]


def test_detail_rejects_non_http_asset_url(rest_module, monkeypatch):
    target, _ = rest_module

    def fake_open(req, timeout):
        if req.full_url.endswith("/search"):
            return Response({"items": [{"link": {"url": "/item/1"}}]}, req.full_url)

        return Response({"files": [{"url": "file:///etc/hosts"}]}, req.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        results_path="items",
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
        },
    )
    mod.run()
    assert not mod.results


def test_detail_cross_origin_does_not_forward_auth(rest_module, monkeypatch):
    target, _ = rest_module
    headers = []

    def fake_open(req, timeout):
        headers.append(dict(req.header_items()))
        if len(headers) == 1:
            return Response(
                {"items": [{"link": {"url": "https://elsewhere.example/item/1"}}]},
                req.full_url,
            )

        return Response({"files": []}, req.full_url)

    monkeypatch.setattr(target, "urlopen", fake_open)
    mod = target.RestAPIModule(
        url="https://test.example/search",
        mode="discover",
        headers={"Authorization": "Bearer private"},
        results_path="items",
        detail={
            "url_field": "link.url",
            "results_path": "files",
            "asset_url_field": "url",
        },
    )
    mod.run()
    assert len(headers) == 1 or not any(
        k.lower() == "authorization" for k in headers[1]
    )
