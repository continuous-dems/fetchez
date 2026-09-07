import pytest

from fetchez import spatial
from fetchez import utils
from fetchez.modules import tnm


SAMPLE_REGION = spatial.Region(-118.65, -118.60, 34.05, 34.10, srs="EPSG:4326")


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.text = text if text is not None else "{}"
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeFetch:
    payload = {"total": 0, "items": []}
    params_seen = []

    def __init__(self, _url):
        pass

    def fetch_req(self, params=None):
        self.__class__.params_seen.append(dict(params or {}))
        return FakeResponse(self.__class__.payload)


@pytest.fixture(autouse=True)
def reset_fake_fetch(monkeypatch):
    FakeFetch.payload = {"total": 0, "items": []}
    FakeFetch.params_seen = []
    monkeypatch.setattr(tnm.core, "Fetch", FakeFetch)


def _item(title, url, publication_date, source_id):
    return {
        "title": title,
        "sourceId": source_id,
        "metaUrl": f"https://example.test/sciencebase/{source_id}",
        "vendorMetaUrl": (
            "https://prd-tnm.s3.amazonaws.com/index.html?prefix="
            "StagedProducts/Elevation/metadata/waf/"
            f"USGS_1M_tile_{source_id}_meta.xml"
        ),
        "publicationDate": publication_date,
        "lastUpdated": f"{publication_date}T12:00:00Z",
        "sizeInBytes": 1234,
        "format": "GeoTIFF",
        "downloadURL": url,
        "boundingBox": {
            "minX": -118.65,
            "maxX": -118.60,
            "minY": 34.05,
            "maxY": 34.10,
        },
    }


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("1m", tnm.DATASET_CODES[2]),
        ("1_9as", tnm.DATASET_CODES[4]),
        ("1_3as", tnm.DATASET_CODES[3]),
        ("1_as", tnm.DATASET_CODES[1]),
        ("2_as", tnm.DATASET_CODES[5]),
        ("5m", tnm.DATASET_CODES[6]),
        ("s1m", tnm.DATASET_CODES[29]),
        ("2", tnm.DATASET_CODES[2]),
        ("8/2", f"{tnm.DATASET_CODES[8]},{tnm.DATASET_CODES[2]}"),
    ],
)
def test_dataset_aliases_keep_existing_numeric_syntax(selector, expected):
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets=selector,
        use_cache=False,
    )
    mod.run()

    assert FakeFetch.params_seen[0]["datasets"] == expected


def test_invalid_dataset_selector_keeps_existing_default():
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="2/not-a-dataset",
        use_cache=False,
    )
    mod.run()

    assert FakeFetch.params_seen[0]["datasets"] == tnm.DATASET_CODES[1]


def test_source_string_syntax_supports_dedupe_false():
    parsed = utils.parse_source_string("tnm:datasets=1m,dedupe=false")

    assert parsed["module"] == "tnm"
    assert parsed["args"]["datasets"] == "1m"
    assert parsed["args"]["dedupe"] is False


def test_default_dedupe_keeps_existing_newest_product_behavior():
    FakeFetch.payload = {
        "total": 2,
        "items": [
            _item(
                "USGS 1 Meter older",
                "https://example.test/Projects/"
                "CA_2025LosAngelesPostWildfire_C25/older/USGS_1M_tile.tif",
                "2024-01-01",
                "older",
            ),
            _item(
                "USGS 1 Meter newer",
                "https://example.test/Projects/"
                "CA_2025LosAngelesPostWildfire_C25/newer/USGS_1M_tile.tif",
                "2025-02-01",
                "newer",
            ),
        ],
    }

    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        use_cache=False,
    )
    mod.run()

    assert len(mod.results) == 1
    assert mod.results[0]["dst_fn"].endswith("/USGS_1M_tile.tif")
    assert mod.results[0]["tnm_source_id"] == "newer"
    assert mod.results[0]["tnm_project"] == "CA_2025LosAngelesPostWildfire_C25"
    assert mod.results[0]["tnm_publication_date"] == "2025-02-01"
    assert mod.results[0]["tnm_last_updated"] == "2025-02-01T12:00:00Z"
    assert mod.results[0]["tnm_meta_url"].endswith("/newer")
    assert "/metadata/waf/" in mod.results[0]["tnm_vendor_meta_url"]


def test_single_dataset_alias_preserves_product_identity():
    FakeFetch.payload = {
        "total": 1,
        "items": [
            _item(
                "USGS Seamless 1 Meter",
                "https://example.test/StagedProducts/Elevation/S1M/test.tif",
                "2026-01-01",
                "s1m-source",
            )
        ],
    }
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="s1m",
        use_cache=False,
    )
    mod.run()

    assert mod.results[0]["tnm_product"] == "s1m"


@pytest.mark.parametrize("product", ["1m", "1_9as"])
def test_source_coverage_uses_the_provider_for_the_selected_product(
    monkeypatch, product
):
    FakeFetch.payload = {
        "total": 1,
        "items": [
            _item(
                "source tile",
                "https://example.test/Projects/ME_Project/USGS_1M_tile.tif",
                "2020-01-01",
                "source",
            )
        ],
    }
    called = []

    def wesm(entries, region, require_year=False):
        called.append(("wesm", require_year))
        return entries

    def ned(entries, region):
        called.append(("ned", False))
        return entries

    monkeypatch.setattr(tnm.WESM, "add_source_coverage", wesm)
    monkeypatch.setattr(tnm.tnm_ned, "add_source_coverage", ned)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets=product,
        source_coverage=True,
        use_cache=False,
    )

    mod.run()

    assert called == ([("wesm", True)] if product == "1m" else [("ned", False)])


def test_dedupe_false_retains_overlapping_products_without_name_collision():
    FakeFetch.payload = {
        "total": 2,
        "items": [
            _item(
                "USGS 1 Meter older",
                "https://example.test/Projects/CA_2024_Test/older/USGS_1M_tile.tif",
                "2024-01-01",
                "older",
            ),
            _item(
                "USGS 1 Meter newer",
                "https://example.test/Projects/"
                "CA_2025LosAngelesPostWildfire_C25/newer/USGS_1M_tile.tif",
                "2025-02-01",
                "newer",
            ),
        ],
    }

    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        dedupe=False,
        use_cache=False,
    )
    mod.run()

    assert len(mod.results) == 2
    assert len({entry["dst_fn"] for entry in mod.results}) == 2
    assert all(entry["dst_fn"].endswith("/USGS_1M_tile.tif") for entry in mod.results)
    assert [entry["tnm_source_id"] for entry in mod.results] == ["older", "newer"]
    assert [entry["tnm_project"] for entry in mod.results] == [
        "CA_2024_Test",
        "CA_2025LosAngelesPostWildfire_C25",
    ]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse({}, status_code=500), "request failed: 500"),
        (
            FakeResponse({"errorMessage": "Search timed out"}),
            "TNM API error: Search timed out",
        ),
        (
            FakeResponse({}, json_error=ValueError("broken")),
            "returned invalid JSON",
        ),
        (FakeResponse({}), "missing total or items"),
    ],
)
def test_provider_failures_raise_and_are_not_cached(
    tmp_path, monkeypatch, response, message
):
    class FailedFetch:
        def __init__(self, _url):
            pass

        def fetch_req(self, params=None):
            return response

    monkeypatch.setattr(tnm.core, "Fetch", FailedFetch)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        outdir=tmp_path,
    )

    with pytest.raises(RuntimeError, match=message):
        mod.run()

    assert not list(tmp_path.rglob("*.json"))


def test_successful_empty_result_is_cacheable(tmp_path):
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        outdir=tmp_path,
    )

    mod.run()

    cache_files = list(tmp_path.rglob("*.json"))
    assert len(cache_files) == 1
    assert cache_files[0].read_text().strip() == "[]"


def test_incomplete_pagination_raises(monkeypatch):
    class PagedFetch:
        calls = 0

        def __init__(self, _url):
            pass

        def fetch_req(self, params=None):
            self.__class__.calls += 1
            items = (
                [
                    _item(
                        "first",
                        "https://example.test/Projects/CA_Test/USGS_1M_tile.tif",
                        "2025-01-01",
                        "first",
                    )
                ]
                if self.calls == 1
                else []
            )
            return FakeResponse({"total": 2, "items": items})

    monkeypatch.setattr(tnm.core, "Fetch", PagedFetch)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        use_cache=False,
    )

    with pytest.raises(RuntimeError, match="stopped after 1 of 2 products"):
        mod.run()


def test_pagination_total_change_raises(monkeypatch):
    class PagedFetch:
        calls = 0

        def __init__(self, _url):
            pass

        def fetch_req(self, params=None):
            self.__class__.calls += 1
            total = 2 if self.calls == 1 else 1
            return FakeResponse(
                {
                    "total": total,
                    "items": [
                        _item(
                            "page item",
                            "https://example.test/Projects/CA_Test/USGS_1M_tile.tif",
                            "2025-01-01",
                            str(self.calls),
                        )
                    ],
                }
            )

    monkeypatch.setattr(tnm.core, "Fetch", PagedFetch)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        use_cache=False,
    )

    with pytest.raises(RuntimeError, match="total changed during pagination"):
        mod.run()


def test_source_coverage_does_not_broaden_rejected_dataset_query(monkeypatch):
    class RejectedFetch:
        calls = 0

        def __init__(self, _url):
            pass

        def fetch_req(self, params=None):
            self.__class__.calls += 1
            return FakeResponse(
                {"errorMessage": "All dataset queries failed"},
                text='{"errorMessage":"All dataset queries failed"}',
            )

    monkeypatch.setattr(tnm.core, "Fetch", RejectedFetch)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        source_coverage=True,
        use_cache=False,
    )

    with pytest.raises(RuntimeError, match="rejected the strict dataset query"):
        mod.run()
    assert RejectedFetch.calls == 1


def test_strict_dataset_query_does_not_broaden_without_source_coverage(monkeypatch):
    class RejectedFetch:
        calls = 0

        def __init__(self, _url):
            pass

        def fetch_req(self, params=None):
            self.__class__.calls += 1
            return FakeResponse(
                {"errorMessage": "All dataset queries failed"},
                text='{"errorMessage":"All dataset queries failed"}',
            )

    monkeypatch.setattr(tnm.core, "Fetch", RejectedFetch)
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="s1m",
        strict_datasets=True,
        use_cache=False,
    )

    with pytest.raises(RuntimeError, match="rejected the strict dataset query"):
        mod.run()
    assert RejectedFetch.calls == 1


def test_source_coverage_is_requested_from_wesm(monkeypatch):
    FakeFetch.payload = {
        "total": 1,
        "items": [
            _item(
                "USGS 1 Meter",
                "https://example.test/Projects/CA_Test/USGS_1M_tile.tif",
                "2025-01-01",
                "source",
            )
        ],
    }
    seen = {}

    def add_source_coverage(entries, region, require_year=False):
        seen["entries"] = entries
        seen["region"] = region
        seen["require_year"] = require_year
        entries[0]["tnm_source_coverage"] = [{"geometry": "POINT (0 0)"}]
        return entries

    monkeypatch.setattr(
        tnm.WESM,
        "add_source_coverage",
        staticmethod(add_source_coverage),
    )
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION,
        datasets="1m",
        source_coverage=True,
        use_cache=False,
    )
    mod.run()

    assert seen["require_year"] is True
    assert seen["region"] == SAMPLE_REGION
    assert len(seen["entries"]) == 1
    assert mod.results[0]["tnm_source_coverage"] == [{"geometry": "POINT (0 0)"}]


def test_missing_download_url_fails_closed():
    FakeFetch.payload = {"total": 1, "items": [{"sourceId": "missing-url"}]}
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, datasets="1m", use_cache=False)
    with pytest.raises(RuntimeError, match="download URL"):
        mod.run()
