"""Use real archived shapefiles and local HTTP range responses."""

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
import shapely
from pyogrio.raw import write
from pyproj import CRS

from fetchez.hooks.remote_archive_footprint import RemoteArchiveFootprintHook
from fetchez.hooks.spatial_cull import SpatialCullHook
from fetchez.hooks.audit import Audit


@pytest.fixture
def remote_archive(tmp_path):
    state = {"payload": b"", "bytes": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(state["payload"])))
            self.end_headers()

        def do_GET(self):
            start, end = map(
                int, self.headers["Range"].removeprefix("bytes=").split("-")
            )
            self.send_response(206)
            self.send_header(
                "Content-Range", f"bytes {start}-{end}/{len(state['payload'])}"
            )
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            state["bytes"] += end - start + 1
            self.wfile.write(state["payload"][start : end + 1])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def make(
        polygons=None, crs="EPSG:4326", missing=None, second=False, prefix="nested"
    ):
        if polygons is None:
            polygons = [
                shapely.box(-124, 43, -123, 44),
                shapely.box(-123, 43, -122, 44),
            ]
        write(
            tmp_path / "source.shp",
            geometry=np.array([shapely.to_wkb(p) for p in polygons], dtype=object),
            field_data=[
                np.array([f"survey-{i}" for i in range(len(polygons))]),
                np.full(len(polygons), 2020, dtype="int32"),
                np.full(len(polygons), np.nan),
            ],
            fields=["project", "year", "score"],
            driver="ESRI Shapefile",
            geometry_type=polygons[0].geom_type,
            crs=CRS(crs).to_wkt(),
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "unrelated.bin", b"x" * 2_000_000, compress_type=zipfile.ZIP_STORED
            )
            for path in tmp_path.glob("source.*"):
                if path.suffix == missing:
                    continue
                archive.write(path, f"{prefix}/source{path.suffix.upper()}")
                if second:
                    archive.write(path, f"other/source{path.suffix.upper()}")
        state["payload"] = buffer.getvalue()
        state["bytes"] = 0
        return f"http://127.0.0.1:{server.server_port}/data.zip", state

    yield make
    server.shutdown()
    server.server_close()
    thread.join()


def test_reads_only_footprints_and_preserves_features(remote_archive):
    url, state = remote_archive()
    module = object()
    entry = {"url": url, "year": 2020, "title": "source"}
    entries = [(module, entry)]
    hook = RemoteArchiveFootprintHook(fields="project")
    assert hook.stage == "manifest"
    assert hook.run(entries) is entries
    assert entry["url"] == url
    assert entry["geometry"].bounds == (-124, 43, -122, 44)
    assert len(entry["footprint_features"]) == 2
    assert entry["footprint_features"][1]["properties"] == {"project": "survey-1"}
    assert entry["footprint_features"][0]["fid"] == 0
    assert entry["footprint_layer"] == "nested/source.SHP"
    json.dumps(Audit()._sanitize(entry), allow_nan=False)
    assert 0 < state["bytes"] < len(state["payload"]) / 4
    newer = (module, {**entry, "year": 2021})
    assert SpatialCullHook().run([*entries, newer]) == [newer]


def test_requires_selection_for_multiple_layers(remote_archive):
    url, _ = remote_archive(second=True)
    with pytest.raises(ValueError, match="Select a footprint layer"):
        RemoteArchiveFootprintHook().run([(None, {"url": url})])
    entry = {"url": url}
    RemoteArchiveFootprintHook(layer="other/source.SHP").run([(None, entry)])
    assert entry["footprint_layer"] == "other/source.SHP"


@pytest.mark.parametrize("suffix", [".shx", ".dbf", ".prj"])
def test_missing_sidecar_does_not_replace_geometry(remote_archive, suffix):
    url, _ = remote_archive(missing=suffix)
    entry = {"url": url, "geometry": "original"}
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        RemoteArchiveFootprintHook().run([(None, entry)])
    assert entry["geometry"] == "original"


def test_missing_field_is_rejected(remote_archive):
    url, _ = remote_archive()
    with pytest.raises(ValueError, match="fields not found"):
        RemoteArchiveFootprintHook(fields="absent").run([(None, {"url": url})])


def test_projected_footprint(remote_archive):
    url, _ = remote_archive([shapely.box(0, 0, 1000, 1000)], crs="EPSG:3857")
    entry = {"url": url}
    RemoteArchiveFootprintHook().run([(None, entry)])
    assert entry["geometry"].bounds == pytest.approx((0, 0, 0.00898315, 0.00898315))


def test_preserves_polygon_holes(remote_archive):
    polygon = shapely.box(-124, 43, -122, 45).difference(
        shapely.box(-123.5, 43.5, -123, 44)
    )
    url, _ = remote_archive([polygon])
    entry = {"url": url}
    RemoteArchiveFootprintHook().run([(None, entry)])
    assert entry["geometry"].equals(polygon)
    properties = entry["footprint_features"][0]["properties"]
    assert properties == {"project": "survey-0", "year": 2020, "score": None}
    assert shapely.from_wkt(entry["footprint_features"][0]["geometry"]).equals(polygon)
    json.dumps(Audit()._sanitize(entry), allow_nan=False)


def test_archive_paths_are_not_extracted_verbatim(remote_archive):
    url, _ = remote_archive(prefix="../../outside")
    entry = {"url": url}
    RemoteArchiveFootprintHook().run([(None, entry)])
    assert entry["geometry"].area == 2


def test_non_polygon_is_rejected(remote_archive):
    url, _ = remote_archive([shapely.Point(0, 0)])
    with pytest.raises(ValueError, match="Invalid footprint polygon"):
        RemoteArchiveFootprintHook().run([(None, {"url": url})])


def test_empty_manifest():
    assert RemoteArchiveFootprintHook().run([]) == []


def test_antimeridian_footprint_is_rejected(remote_archive):
    url, _ = remote_archive([shapely.box(179, 0, 181, 1)])
    with pytest.raises(ValueError, match="WGS84 limits"):
        RemoteArchiveFootprintHook().run([(None, {"url": url})])
