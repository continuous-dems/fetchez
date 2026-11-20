"""Discovery and inventory tests for generic FRED-backed sources."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from shapely.geometry import shape

from fetchez import config, fred
from fetchez.hooks.inventory import Inventory
from fetchez.modules.http_index import HTTPIndex
from fetchez.modules.local import Local
from fetchez.spatial import Region


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / ".fetchez")


def test_local_index_preserves_feature_geometry_in_inventory(tmp_path):
    index_path = tmp_path / "local-surveys.geojson"
    index = fred.FRED("local-surveys", path=index_path)
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-120, 32], [-118, 32], [-119, 33], [-120, 32]]],
    }
    index.add_survey(
        polygon, Name="survey.tif", DataLink="https://example.invalid/survey.tif"
    )
    index.add_survey(
        None, Name="no-coverage.tif", DataLink="https://example.invalid/no-coverage.tif"
    )
    index.save()

    legacy_results = index.search()
    assert "geometry" not in legacy_results[0]
    assert index.search(return_features=True)[0]["geometry"] == polygon
    assert index.search() == legacy_results

    for reference in ("local-surveys", str(index_path)):
        source = Local(index=reference, use_cache=False).run()
        known, unknown = source.results
        assert known["geometry"].equals(shape(polygon))
        assert known["geometry_crs"] == "EPSG:4326"
        assert known["geometry_source"] == "fred_index_feature"
        assert "geometry" not in unknown

    output = tmp_path / "inventory.geojson"
    Inventory(output=output).run([(source, entry) for entry in source.results])
    features = json.loads(output.read_text(encoding="utf-8"))["features"]
    assert shape(features[0]["geometry"]).equals(shape(polygon))
    assert features[1]["geometry"] is None


@pytest.mark.parametrize(
    "geometry",
    [None, {"type": "Polygon", "coordinates": []}, {"type": "Polygon"}],
)
def test_unusable_index_geometry_is_optional(geometry):
    assert fred.entry_geometry_fields(geometry) == {}


def test_http_geometry_is_available_from_the_crawl_and_cached_index(tmp_path):
    requests = []

    class Catalog(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path != "/catalog/":
                self.send_error(404)
                return
            content = (
                b'<a href="tile_10_20.tif">Tile</a><a href="unknown.tif">No bounds</a>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    with ThreadingHTTPServer(("127.0.0.1", 0), Catalog) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            options = {
                "url": f"http://127.0.0.1:{server.server_port}/catalog/",
                "pattern": "*.tif",
                "index_path": tmp_path / "tiles.geojson",
                "footprint": {
                    "method": "filename",
                    "regex": r"tile_(?P<x>\d+)_(?P<y>\d+)\.tif",
                    "width": 2,
                    "height": 2,
                },
                "use_cache": False,
            }
            built = HTTPIndex(index=True, **options).run()
            cached = HTTPIndex(
                index=True, region=Region(10, 11, 20, 21), **options
            ).run()
            assert requests == ["/catalog/"]
            for source in (built, cached):
                (entry,) = source.results
                assert entry["geometry"].bounds == (10, 20, 12, 22)
                assert entry["geometry_crs"] == "EPSG:4326"

            direct = HTTPIndex(**options).run()
            known, unknown = direct.results
            assert known["geometry"].equals(built.results[0]["geometry"])
            assert known["geometry_kind"] == "bounding_box"
            assert "geometry" not in unknown
            assert requests == ["/catalog/", "/catalog/"]
        finally:
            server.shutdown()
            worker.join()
