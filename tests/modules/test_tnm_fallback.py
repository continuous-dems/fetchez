"""Fallback discovery for the tnm module: what happens when the TNM API fails."""

import hashlib
import json
import logging

import pytest

from fetchez import spatial
from fetchez.hooks.spatial_cull import SpatialCullHook
from fetchez.modules import tnm

NED_1 = tnm.DATASET_CODES[1]
NED_13 = tnm.DATASET_CODES[3]

# A box well inside cell n36w120 (35-36N, 120-119W).
REGION = spatial.Region(-119.6, -119.4, 35.4, 35.6, srs="EPSG:4326")

# The body the API answered with, HTTP 200, during the September 2026 outage.
OUTAGE_BODY = {
    "error": "Expecting value: line 1 column 1 (char 0)",
    "showToast": True,
    "toastMessage": "Expecting value: line 1 column 1 (char 0)",
    "toastType": "warning",
}

S3 = tnm.TNM_S3_URL
HIST_1 = "StagedProducts/Elevation/1/TIFF/historical/n36w120/"
CURR_1 = "StagedProducts/Elevation/1/TIFF/current/n36w120/"

# What the API returned for n36w120, 1 arc-second, on 2026-09-16 (url, dst_fn).
RECORDED_API_N36W120 = [
    (f"{S3}{HIST_1}USGS_1_n36w120_{stamp}.tif", f"USGS_1_n36w120_{stamp}.tif")
    for stamp in (
        "20190919",
        "20210607",
        "20210610",
        "20240207",
        "20250515",
        "20250826",
    )
]

# What the bucket listed for the same cell: the tifs plus their sidecar files.
S3_N36W120 = {
    HIST_1: [
        (f"{HIST_1}USGS_1_n36w120_{stamp}.{ext}", size, modified)
        for stamp, size, modified in (
            ("20190919", 48945340, "2022-12-03T01:00:00.000Z"),
            ("20210607", 48851228, "2022-12-03T01:00:00.000Z"),
            ("20210610", 49221575, "2022-12-03T01:00:00.000Z"),
            ("20240207", 52130443, "2024-02-07T01:00:00.000Z"),
            ("20250515", 52130883, "2025-05-15T01:00:00.000Z"),
            ("20250826", 51990394, "2025-08-27T01:00:00.000Z"),
        )
        for ext in ("tif", "xml", "jpg")
    ],
    CURR_1: [(f"{CURR_1}USGS_1_n36w120.tif", 51990394, "2025-08-27T01:00:00.000Z")],
}


def _listing(objects, truncated=False, token=None):
    contents = "".join(
        f"<Contents><Key>{key}</Key><LastModified>{modified}</LastModified>"
        f"<Size>{size}</Size></Contents>"
        for key, size, modified in objects
    )
    more = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>{more}"
        f"{contents}</ListBucketResult>"
    ).encode()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self.payload = payload
        self.content = content
        self.text = json.dumps(payload) if payload is not None else content.decode()

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


class FakeFetch:
    """Serves the products API and the S3 bucket listing, by URL."""

    api = FakeResponse(payload=OUTAGE_BODY)
    api_pages = None
    bucket = {}
    s3_status = 200
    s3_prefixes_seen = []

    def __init__(self, url):
        self.url = url

    def fetch_req(self, params=None):
        cls = self.__class__
        if self.url != S3:
            if cls.api_pages is not None:
                return cls.api_pages.pop(0)
            return cls.api
        prefix = params["prefix"]
        cls.s3_prefixes_seen.append(prefix)
        if cls.s3_status != 200:
            return FakeResponse(status_code=cls.s3_status)
        return FakeResponse(content=_listing(cls.bucket.get(prefix, [])))


@pytest.fixture(autouse=True)
def fake_fetch(monkeypatch):
    FakeFetch.api = FakeResponse(payload=OUTAGE_BODY)
    FakeFetch.api_pages = None
    FakeFetch.bucket = dict(S3_N36W120)
    FakeFetch.s3_status = 200
    FakeFetch.s3_prefixes_seen = []
    monkeypatch.setattr(tnm.core, "Fetch", FakeFetch)


def _module(**kwargs):
    kwargs.setdefault("src_region", REGION)
    kwargs.setdefault("use_cache", False)
    return tnm.TheNationalMap(**kwargs)


def _levels(caplog, level):
    return [r.getMessage() for r in caplog.records if r.levelno == level]


# -----------------------------------------------------------------------------
# NED cell names
# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        # Interior of one cell; the name is the north-west corner.
        ((-119.6, -119.4, 35.4, 35.6), ["n36w120"]),
        # Spans a corner: four cells.
        (
            (-120.1, -119.9, 34.9, 35.1),
            ["n35w121", "n35w120", "n36w121", "n36w120"],
        ),
        # Touching a cell edge pulls in the neighbour, whose overlap reaches it.
        ((-119.6, -119.4, 35.0, 35.2), ["n35w120", "n36w120"]),
        # Southern and eastern hemispheres (American Samoa, Guam).
        ((-170.8, -170.6, -14.4, -14.2), ["s14w171"]),
        ((144.6, 144.9, 13.2, 13.6), ["n14e144"]),
    ],
)
def test_ned_cells_are_named_for_their_north_west_corner(bounds, expected):
    names = [name for name, _west, _south in tnm._ned_cells(*bounds, pad=6 / 3600)]
    assert names == expected


def test_ned_cell_origin_is_its_south_west_corner():
    assert list(tnm._ned_cells(-119.6, -119.4, 35.4, 35.6, pad=0)) == [
        ("n36w120", -120, 35)
    ]


# -----------------------------------------------------------------------------
# S3 listing
# -----------------------------------------------------------------------------
def test_s3_list_follows_continuation_tokens(monkeypatch):
    pages = [
        _listing(
            [("a.tif", 1, "2025-01-01T00:00:00.000Z")], truncated=True, token="t1"
        ),
        _listing([("b.tif", 2, "2025-01-02T00:00:00.000Z")]),
    ]
    seen = []

    def fetch_req(self, params=None):
        seen.append(dict(params))
        return FakeResponse(content=pages.pop(0))

    monkeypatch.setattr(FakeFetch, "fetch_req", fetch_req)

    assert [key for key, _size, _modified in tnm._s3_list("p/")] == ["a.tif", "b.tif"]
    assert "continuation-token" not in seen[0]
    assert seen[1]["continuation-token"] == "t1"


def test_s3_list_empty_listing_is_a_valid_answer():
    assert tnm._s3_list("StagedProducts/Elevation/1/TIFF/historical/n35w122/") == []


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=503),
        None,
        FakeResponse(content=b"<html>Service Unavailable"),
        FakeResponse(content=b"<Error><Code>SlowDown</Code></Error>"),
        FakeResponse(
            content=_listing([("a.tif", 1, "2025-01-01T00:00:00.000Z")], truncated=True)
        ),
    ],
    ids=["http-error", "no-response", "not-xml", "s3-error-document", "cut-short"],
)
def test_s3_list_never_reads_a_failure_as_no_data(monkeypatch, response):
    monkeypatch.setattr(FakeFetch, "fetch_req", lambda self, params=None: response)
    with pytest.raises(RuntimeError):
        tnm._s3_list("p/")


# -----------------------------------------------------------------------------
# Fallback results match what the API returns
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("strict", [False, True])
def test_outage_body_falls_back_to_the_same_urls_and_filenames(strict):
    mod = _module(datasets="1", formats="GeoTIFF", strict_datasets=strict)
    mod.run()

    got = [(e["url"], e["dst_fn"].rsplit("/", 1)[-1]) for e in mod.results]
    assert got == RECORDED_API_N36W120
    # `current/` holds a copy of the newest dated file; the API never lists it.
    assert FakeFetch.s3_prefixes_seen == [HIST_1]


def test_products_mode_names_files_as_the_api_path_does():
    mod = _module(products="1_as")
    mod.run()

    url, filename = RECORDED_API_N36W120[-1]
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    assert mod.results[-1]["dst_fn"].endswith(f"/1_as/{digest}/{filename}")
    assert {e["tnm_product"] for e in mod.results} == {"1_as"}
    assert {e["tnm_dataset"] for e in mod.results} == {NED_1}


def test_fallback_entries_carry_what_downstream_hooks_read():
    mod = _module(datasets="1")
    mod.run()

    newest = mod.results[-1]
    assert newest["metadata"]["date"] == "2025-08-26"
    assert newest["metadata"]["title"] == "USGS 1 Arc Second n36w120 20250826"
    assert newest["remote_size"] == 51990394
    assert newest["format"] == "GeoTIFF"
    assert newest["data_type"] == "tnm"
    assert newest["tnm_discovery"] == "the prd-tnm S3 listing"
    west, east, south, north = newest["bounds"]
    assert (west, east, south, north) == pytest.approx(
        (-120 - 6 / 3600, -119 + 6 / 3600, 35 - 6 / 3600, 36 + 6 / 3600)
    )
    assert newest["geometry"].bounds == pytest.approx((west, south, east, north))


def test_spatial_cull_keeps_only_the_newest_fallback_version():
    mod = _module(datasets="1")
    mod.run()

    hook = SpatialCullHook(sort_by="date", reverse=True, min_coverage=0.98)
    kept = hook.run([(mod, entry) for entry in mod.results])

    assert [entry["url"] for _mod, entry in kept] == [RECORDED_API_N36W120[-1][0]]


def test_cell_without_dated_versions_uses_current():
    FakeFetch.bucket = {CURR_1: S3_N36W120[CURR_1]}
    mod = _module(datasets="1")
    mod.run()

    assert [e["url"] for e in mod.results] == [f"{S3}{CURR_1}USGS_1_n36w120.tif"]
    assert mod.results[0]["metadata"]["date"] == "2025-08-27"
    assert FakeFetch.s3_prefixes_seen == [HIST_1, CURR_1]


def test_both_datasets_in_one_query_are_each_discovered():
    hist_13 = "StagedProducts/Elevation/13/TIFF/historical/n36w120/"
    FakeFetch.bucket[hist_13] = [
        (
            f"{hist_13}USGS_13_n36w120_20250826.tif",
            433457115,
            "2025-08-27T01:00:00.000Z",
        )
    ]
    mod = _module(datasets="1/3")
    mod.run()

    assert len(mod.results) == 7
    assert (
        mod.results[-1]["metadata"]["title"] == "USGS 1/3 Arc Second n36w120 20250826"
    )
    # As on the API path, entries are only labelled when one dataset was queried.
    assert {e["tnm_product"] for e in mod.results} == {None}


def test_a_failure_part_way_through_pagination_keeps_no_partial_results():
    page = {
        "total": 2,
        "items": [
            {
                "downloadURL": "https://example.test/half/an_answer.tif",
                "publicationDate": "2025-01-01",
            }
        ],
    }
    FakeFetch.api_pages = [
        FakeResponse(payload=page),
        FakeResponse(payload=OUTAGE_BODY),
    ]
    mod = _module(datasets="1", strict_datasets=True)
    mod.run()

    assert [e["url"] for e in mod.results] == [url for url, _fn in RECORDED_API_N36W120]


# -----------------------------------------------------------------------------
# API failures are recognised in both modes
# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(payload=OUTAGE_BODY),
        FakeResponse(payload={"items": []}),
        FakeResponse(payload={"total": 0}),
        FakeResponse(payload=["not", "a", "dict"]),
        FakeResponse(content=b"{errorMessage: upstream timeout}"),
        FakeResponse(content=b"<html>Bad Gateway</html>"),
        FakeResponse(status_code=502),
        None,
    ],
    ids=[
        "error-key",
        "no-total",
        "no-items",
        "not-a-dict",
        "errorMessage",
        "not-json",
        "http-error",
        "no-response",
    ],
)
@pytest.mark.parametrize("strict", [False, True])
def test_every_kind_of_api_failure_reaches_the_fallback(response, strict):
    FakeFetch.api = response
    mod = _module(datasets="1", strict_datasets=strict)
    mod.run()
    assert len(mod.results) == len(RECORDED_API_N36W120)


def test_a_genuine_empty_answer_is_not_a_failure(caplog):
    FakeFetch.api = FakeResponse(payload={"total": 0, "items": []})
    with caplog.at_level(logging.INFO, logger=tnm.logger.name):
        mod = _module(datasets="1")
        mod.run()

    assert mod.results == []
    assert FakeFetch.s3_prefixes_seen == []
    assert not getattr(mod, "_discovery_failed", False)
    assert _levels(caplog, logging.WARNING) == []
    assert _levels(caplog, logging.ERROR) == []


# -----------------------------------------------------------------------------
# Logging contract
# -----------------------------------------------------------------------------
def test_using_a_fallback_warns_exactly_once_and_reports_the_count(caplog):
    with caplog.at_level(logging.INFO, logger=tnm.logger.name):
        _module(datasets="1").run()

    warnings = _levels(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "TNM API unavailable" in warnings[0]
    assert NED_1 in warnings[0]
    assert "the prd-tnm S3 listing" in warnings[0]
    assert "may differ slightly" in warnings[0]
    assert _levels(caplog, logging.ERROR) == []
    assert f"Fallback discovery found 6 product(s) for {NED_1}." in _levels(
        caplog, logging.INFO
    )


def test_a_fallback_that_finds_nothing_says_so(caplog):
    FakeFetch.bucket = {}
    with caplog.at_level(logging.INFO, logger=tnm.logger.name):
        mod = _module(datasets="1")
        mod.run()

    assert mod.results == []
    assert not getattr(mod, "_discovery_failed", False)
    assert f"Fallback discovery found 0 product(s) for {NED_1}." in _levels(
        caplog, logging.INFO
    )


@pytest.mark.parametrize("selector", ["1_9as", "2_as", "5m", "s1m", "8", "11"])
def test_dataset_without_a_fallback_logs_an_error(caplog, selector):
    with caplog.at_level(logging.INFO, logger=tnm.logger.name):
        mod = _module(datasets=selector)
        mod.run()

    assert mod.results == []
    assert mod._discovery_failed is True
    assert _levels(caplog, logging.WARNING) == []
    errors = _levels(caplog, logging.ERROR)
    assert len(errors) == 1
    assert "no fallback discovery exists for" in errors[0]
    assert "not cached" in errors[0]
    assert FakeFetch.s3_prefixes_seen == []


def test_one_uncovered_dataset_blocks_the_whole_query(caplog):
    with caplog.at_level(logging.ERROR, logger=tnm.logger.name):
        mod = _module(datasets="1/1_9as")
        mod.run()

    assert mod.results == []
    assert tnm.DATASET_CODES[4] in _levels(caplog, logging.ERROR)[0]
    assert NED_1 not in _levels(caplog, logging.ERROR)[0].split("exists for")[1]


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"q": "lidar"}, "cannot apply q, extents or date filters"),
        ({"extents": "1 x 1 degree"}, "cannot apply q, extents or date filters"),
        ({"date_start": "2024-01-01"}, "cannot apply q, extents or date filters"),
        ({"formats": "IMG"}, "only finds GeoTIFF"),
        ({"formats": "GeoTIFF/IMG"}, "only finds GeoTIFF"),
    ],
)
def test_queries_the_fallback_cannot_honour_log_an_error(caplog, kwargs, fragment):
    with caplog.at_level(logging.ERROR, logger=tnm.logger.name):
        mod = _module(datasets="1", **kwargs)
        mod.run()

    assert mod.results == []
    assert mod._discovery_failed is True
    assert fragment in _levels(caplog, logging.ERROR)[0]


def test_a_failing_fallback_logs_an_error_and_returns_nothing(caplog):
    FakeFetch.s3_status = 503
    with caplog.at_level(logging.INFO, logger=tnm.logger.name):
        mod = _module(datasets="1")
        mod.run()

    assert mod.results == []
    assert mod._discovery_failed is True
    errors = _levels(caplog, logging.ERROR)
    assert len(errors) == 1
    assert "fallback discovery failed" in errors[0]
    assert "503" in errors[0]


@pytest.mark.parametrize(
    "setup",
    [
        {"datasets": "1_9as"},
        {"datasets": "1", "q": "lidar"},
        {"datasets": "1", "s3": 503},
    ],
    ids=["no-fallback", "filtered", "fallback-fails"],
)
def test_strict_mode_raises_when_nothing_can_be_discovered(setup):
    FakeFetch.s3_status = setup.pop("s3", 200)
    mod = _module(strict_datasets=True, **setup)
    with pytest.raises(tnm.TNMApiError, match="TNM API unavailable"):
        mod.run()
    assert mod.results == []


def test_tnm_api_error_is_a_runtime_error():
    # Callers that already catch RuntimeError from strict queries keep working.
    assert issubclass(tnm.TNMApiError, RuntimeError)


# -----------------------------------------------------------------------------
# Caching
# -----------------------------------------------------------------------------
def _cache_files(tmp_path):
    return list((tmp_path / "tnm" / ".fetchez_cache").glob("*.json"))


def test_a_failed_discovery_is_not_cached(tmp_path):
    mod = _module(datasets="1_9as", outdir=str(tmp_path), use_cache=True)
    mod.run()

    assert mod.results == []
    assert _cache_files(tmp_path) == []


def test_a_successful_fallback_is_cached_like_an_api_answer(tmp_path):
    mod = _module(datasets="1", outdir=str(tmp_path), use_cache=True)
    mod.run()

    (cache_file,) = _cache_files(tmp_path)
    cached = json.loads(cache_file.read_text())
    assert [entry["dst_fn"] for entry in cached] == [
        fn for _url, fn in RECORDED_API_N36W120
    ]

    # The next run replays the cache and touches neither the API nor S3.
    FakeFetch.s3_prefixes_seen = []
    again = _module(datasets="1", outdir=str(tmp_path), use_cache=True)
    again.run()
    assert len(again.results) == len(RECORDED_API_N36W120)
    assert FakeFetch.s3_prefixes_seen == []


def test_a_genuine_empty_answer_is_still_cached(tmp_path):
    FakeFetch.api = FakeResponse(payload={"total": 0, "items": []})
    mod = _module(datasets="1", outdir=str(tmp_path), use_cache=True)
    mod.run()

    (cache_file,) = _cache_files(tmp_path)
    assert json.loads(cache_file.read_text()) == []
