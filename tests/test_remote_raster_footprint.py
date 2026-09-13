"""Exercise manifest footprints using real TIFFs and local HTTP range reads."""

import multiprocessing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fetchez.hooks.remote_raster_footprint import RemoteRasterFootprintHook
from fetchez.hooks.spatial_cull import SpatialCullHook

rasterio = pytest.importorskip("rasterio")
np = pytest.importorskip("numpy")
Affine = rasterio.Affine


@pytest.fixture
def remote_raster():
    processes = []

    def make(crs="EPSG:4326", affine=None, size=10):
        if affine is None:
            resolution = 1 / size
            affine = Affine(resolution, 0, -124, 0, -resolution, 44)
        with rasterio.io.MemoryFile() as memory:
            with memory.open(
                driver="GTiff",
                width=size,
                height=size,
                count=1,
                dtype="uint8",
                crs=crs,
                transform=affine,
                nodata=0,
            ) as source:
                # Entirely NoData: the footprint must still cover the outer edges.
                source.write(np.zeros((1, size, size), dtype="uint8"))
            payload = memory.read()
        ready_parent, ready_child = multiprocessing.Pipe(duplex=False)
        requests_parent, requests_child = multiprocessing.Pipe(duplex=False)

        def serve():
            class Handler(BaseHTTPRequestHandler):
                def do_HEAD(self):
                    if self.path != "/example.tif":
                        self.send_response(404)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()

                def do_GET(self):
                    if self.path != "/example.tif":
                        self.send_response(404)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    requested = self.headers["Range"]
                    requests_child.send(requested)
                    start, end = map(int, requested.removeprefix("bytes=").split("-"))
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{end}/{len(payload)}"
                    )
                    self.send_header("Content-Length", str(end - start + 1))
                    self.end_headers()
                    self.wfile.write(payload[start : end + 1])

                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            ready_child.send(server.server_port)
            server.serve_forever()

        process = multiprocessing.Process(target=serve, daemon=True)
        process.start()
        processes.append(process)
        port = ready_parent.recv()
        return (
            f"http://127.0.0.1:{port}/example.tif",
            requests_parent,
            len(payload),
        )

    yield make
    for process in processes:
        process.terminate()
        process.join()


def test_extent_preserves_nodata_and_chains_with_cull(remote_raster):
    url, request_pipe, size = remote_raster(size=2048)
    module = object()
    entries = [(module, {"url": url, "year": year}) for year in (2020, 2021)]
    hook = RemoteRasterFootprintHook()
    assert hook.stage == "manifest"
    assert hook.run(entries) is entries
    assert entries[0][0] is module
    assert entries[0][1]["geometry"].bounds == pytest.approx((-124, 43, -123, 44))
    assert entries[0][1]["geometry"].area == pytest.approx(1)
    requests = []
    while request_pipe.poll():
        requests.append(request_pipe.recv())
    assert requests
    transferred = sum(
        int(end) - int(start.removeprefix("bytes=")) + 1
        for start, end in (request.split("-") for request in requests)
    )
    assert transferred < size / 4
    assert SpatialCullHook().run(entries) == [entries[1]]


def test_rotated_extent_is_not_bounding_rectangle(remote_raster):
    url, _, _ = remote_raster(affine=Affine(0.1, 0.02, -124, 0.02, -0.1, 44))
    entry = {"url": url}
    RemoteRasterFootprintHook().run([(None, entry)])
    assert entry["geometry"].area == pytest.approx(1.04)
    assert entry["geometry"].area < entry["geometry"].envelope.area


def test_projected_raster_returns_longitude_latitude(remote_raster):
    url, _, _ = remote_raster("EPSG:3857", Affine(100, 0, 0, 0, -100, 1000))
    entry = {"url": url}
    RemoteRasterFootprintHook().run([(None, entry)])
    assert entry["geometry"].bounds == pytest.approx((0, 0, 0.00898315, 0.00898315))


def test_missing_crs_does_not_replace_geometry(remote_raster):
    url, _, _ = remote_raster(crs=None)
    entry = {"url": url, "geometry": "original"}
    with pytest.raises(ValueError, match="no CRS"):
        RemoteRasterFootprintHook().run([(None, entry)])
    assert entry["geometry"] == "original"


def test_empty_manifest():
    assert RemoteRasterFootprintHook().run([]) == []


def test_antimeridian_extent_is_rejected(remote_raster):
    url, _, _ = remote_raster(affine=Affine(0.2, 0, 179, 0, -0.1, 44))
    with pytest.raises(ValueError, match="WGS84 limits"):
        RemoteRasterFootprintHook().run([(None, {"url": url})])
