import pytest

from fetchez import spatial
from fetchez.modules import tnm
from fetchez.hooks.spatial_cull import SpatialCullHook

SAMPLE_REGION = spatial.Region(-118.65, -118.60, 34.05, 34.10, srs="EPSG:4326")


class FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, payload):
        self.payload = payload

    def json(self):
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
        ("s1m", tnm.DATASET_CODES[29]),
        ("5m", tnm.DATASET_CODES[6]),
        ("2_as", tnm.DATASET_CODES[5]),
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


def test_tnm_natively_yields_all_overlapping_products():
    """Prove TNM no longer arbitrarily drops overlapping items (formerly dedupe=False)."""
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
                "https://example.test/Projects/CA_2025_Test/newer/USGS_1M_tile.tif",
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

    # TNM should now natively return both items without dropping any
    assert len(mod.results) == 2
    assert [entry["tnm_source_id"] for entry in mod.results] == ["older", "newer"]


def test_spatial_cull_hook_retains_newest_tnm_product():
    """Prove the spatial_cull hook correctly filters the raw TNM stream by date."""
    FakeFetch.payload = {
        "total": 2,
        "items": [
            _item(
                "USGS 1 Meter older",
                "https://example.test/Projects/CA_2025_Test/older/USGS_1M_tile.tif",
                "2024-01-01",
                "older",
            ),
            _item(
                "USGS 1 Meter newer",
                "https://example.test/Projects/CA_2025_Test/newer/USGS_1M_tile.tif",
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

    # Format the results exactly as the pipeline runner passes them to hooks
    hook_payload = [(mod, entry) for entry in mod.results]

    # Initialize the hook to sort by 'date' (which TNM populates from publicationDate)
    hook = SpatialCullHook(sort_by="date", reverse=True, min_coverage=0.99)
    culled_results = hook.run(hook_payload)

    # The hook should drop the older item because the bounding boxes match 100%
    assert len(culled_results) == 1

    kept_mod, kept_entry = culled_results[0]
    assert kept_entry["tnm_source_id"] == "newer"
    assert kept_entry["metadata"]["date"] == "2025-02-01"


def _pages(monkeypatch, payloads):
    pages = iter(payloads)

    def fetch_req(self, params=None):
        FakeFetch.params_seen.append(dict(params or {}))
        payload = next(pages)
        return payload if isinstance(payload, FakeResponse) else FakeResponse(payload)

    monkeypatch.setattr(FakeFetch, "fetch_req", fetch_req)


def test_products_query_separately_and_preserve_source_metadata(monkeypatch):
    item = _item(
        "Project tile",
        "https://example.test/Projects/CA%20Survey/tile.tif",
        "2024-01-01",
        "source",
    )
    _pages(monkeypatch, [{"total": 1, "items": [item]}, {"total": 1, "items": [item]}])
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION, products="1m/1_3as", use_cache=False
    )
    mod.run()
    assert [p["datasets"] for p in FakeFetch.params_seen] == [
        tnm.DATASET_CODES[2],
        tnm.DATASET_CODES[3],
    ]
    assert [entry["tnm_product"] for entry in mod.results] == ["1m", "1_3as"]
    assert [entry["tnm_dataset"] for entry in mod.results] == [
        tnm.DATASET_CODES[2],
        tnm.DATASET_CODES[3],
    ]
    assert mod.results[0]["tnm_project"] == "CA Survey"
    assert mod.results[0]["tnm_source_id"] == "source"
    assert mod.results[0]["tnm_publication_date"] == "2024-01-01"
    assert mod.results[0]["tnm_vendor_meta_url"] == item["vendorMetaUrl"]
    assert mod.results[0]["dst_fn"] != mod.results[1]["dst_fn"]
    assert mod.results[0]["geometry"].bounds == (-118.65, 34.05, -118.60, 34.10)


def test_products_keep_distinct_urls_with_same_filename():
    FakeFetch.payload = {
        "total": 2,
        "items": [
            _item("old", "https://example.test/Projects/old/tile.tif", "2020", "old"),
            _item("new", "https://example.test/Projects/new/tile.tif", "2021", "new"),
        ],
    }
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, products="1m", use_cache=False)
    mod.run()
    assert len({entry["dst_fn"] for entry in mod.results}) == 2
    assert len(mod.results) == 2


@pytest.mark.parametrize("products", ["unknown", "1m/unknown", "", []])
def test_invalid_products_never_fall_back(products):
    with pytest.raises(ValueError, match="Unknown TNM products"):
        tnm.TheNationalMap(src_region=SAMPLE_REGION, products=products)
    assert not FakeFetch.params_seen


def test_products_and_datasets_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either products or datasets"):
        tnm.TheNationalMap(src_region=SAMPLE_REGION, products="1m", datasets="2")


def test_product_list_deduplicates_without_reordering():
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION, products=["5m", "1m", "5m"], use_cache=False
    )
    mod.run()
    assert [p["datasets"] for p in FakeFetch.params_seen] == [
        tnm.DATASET_CODES[6],
        tnm.DATASET_CODES[2],
    ]


@pytest.mark.parametrize("selector", ["2/unknown", "99", "-1"])
def test_strict_dataset_validation(selector):
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION, datasets=selector, strict_datasets=True
    )
    with pytest.raises(ValueError, match="Invalid TNM datasets"):
        mod.run()
    assert not FakeFetch.params_seen


def test_strict_query_rejection_does_not_broaden(monkeypatch):
    response = FakeResponse({})
    response.text = "All dataset queries failed"
    response.status_code = 400
    _pages(monkeypatch, [response])
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, products="s1m", use_cache=False)
    with pytest.raises(RuntimeError, match="rejected"):
        mod.run()
    assert len(FakeFetch.params_seen) == 1
    assert mod.results == []


@pytest.mark.parametrize(
    "second",
    [
        {"total": 2, "items": []},
        {"total": 3, "items": []},
        {"errorMessage": "failed"},
        {"total": 2, "items": [{"title": "missing URL"}]},
    ],
)
def test_incomplete_discovery_rolls_back_results(monkeypatch, second):
    item = _item("tile", "https://example.test/tile.tif", "2020", "id")
    _pages(monkeypatch, [{"total": 2, "items": [item]}, second])
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, products="1m", use_cache=False)
    with pytest.raises(RuntimeError):
        mod.run()
    assert mod.results == []
    assert FakeFetch.params_seen[1]["offset"] == 1


def test_short_pages_are_not_skipped(monkeypatch):
    items = [
        _item(str(i), f"https://example.test/{i}.tif", "2020", str(i)) for i in range(2)
    ]
    _pages(monkeypatch, [{"total": 2, "items": [item]} for item in items])
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, products="1m", use_cache=False)
    mod.run()
    assert len(mod.results) == 2
    assert [p["offset"] for p in FakeFetch.params_seen] == [0, 1]


def test_repeated_page_is_rejected(monkeypatch):
    item = _item("tile", "https://example.test/tile.tif", "2020", "id")
    _pages(monkeypatch, [{"total": 2, "items": [item]}] * 2)
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, products="1m", use_cache=False)
    with pytest.raises(RuntimeError, match="repeated"):
        mod.run()
    assert mod.results == []


def test_later_product_failure_rolls_back_earlier_product(monkeypatch):
    item = _item("tile", "https://example.test/tile.tif", "2020", "id")
    _pages(monkeypatch, [{"total": 1, "items": [item]}, {"errorMessage": "failed"}])
    mod = tnm.TheNationalMap(
        src_region=SAMPLE_REGION, products="1m/1_as", use_cache=False
    )
    with pytest.raises(RuntimeError):
        mod.run()
    assert mod.results == []


def test_legacy_fallback_does_not_assign_product_identity(monkeypatch):
    rejected = FakeResponse({})
    rejected.text = "All dataset queries failed"
    item = _item("tile", "https://example.test/tile.tif", "2020", "id")
    _pages(monkeypatch, [rejected, {"total": 1, "items": [item]}])
    mod = tnm.TheNationalMap(src_region=SAMPLE_REGION, datasets="1m", use_cache=False)
    mod.run()
    assert "datasets" not in FakeFetch.params_seen[1]
    assert mod.results[0]["tnm_product"] is None
    assert mod.results[0]["tnm_dataset"] is None
