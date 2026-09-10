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
