# tests/hooks/test_spatial_cull.py

from shapely.geometry import box
import shapely.wkt
import shapely.wkb

from fetchez.modules.base import FetchModule
from fetchez.hooks.spatial_cull import SpatialCullHook


def test_cull_respects_minimum_coverage_threshold():
    """Prove that tiles are only dropped if their overlap exceeds min_coverage."""
    # Poly A is a 10x10 square
    poly_a = box(0, 0, 10, 10)
    # Poly B is a 10x10 square shifted right by 5 units (50% overlap)
    poly_b = box(5, 0, 15, 10)
    # Poly C is entirely contained inside Poly A
    poly_c = box(2, 2, 8, 8)

    entries = [
        ("mod", {"title": "Tile_A", "year": "2020", "geometry": poly_a}),
        ("mod", {"title": "Tile_B", "year": "2019", "geometry": poly_b}),
        ("mod", {"title": "Tile_C", "year": "2018", "geometry": poly_c}),
    ]

    hook = SpatialCullHook(sort_by="year", reverse=True, min_coverage=0.95)
    culled = hook.run(entries)

    titles = [entry["title"] for _, entry in culled]

    # Tile_A should be kept (highest priority).
    # Tile_B should be kept (only 50% covered by A, which is < 95% threshold).
    # Tile_C should be dropped (100% covered by A).
    assert "Tile_A" in titles
    assert "Tile_B" in titles
    assert "Tile_C" not in titles
    assert len(culled) == 2


def test_cull_sorts_by_numeric_resolution():
    """Prove the hook properly sorts by floats rather than just strings."""
    entries = [
        (
            "mod",
            {"title": "Coarse", "resolution": "10.5", "geometry": box(0, 0, 10, 10)},
        ),
        ("mod", {"title": "Fine", "resolution": "1.0", "geometry": box(0, 0, 10, 10)}),
    ]

    # Sort ascending so lower resolution values (higher quality) are processed first
    hook = SpatialCullHook(sort_by="resolution", reverse=False)
    culled = hook.run(entries)

    assert len(culled) == 1
    assert culled[0][1]["title"] == "Fine"


def test_cull_parses_raw_wkb_and_bbox():
    """Prove the hook successfully coerces raw bytes (like DAV yields) and raw bbox lists."""
    geom_poly = box(0, 0, 10, 10)
    geom_wkb = shapely.wkb.dumps(geom_poly)

    entries = [
        # Provides raw WKB bytes
        ("dav", {"title": "WKB_Tile", "year": 2020, "geometry": geom_wkb}),
        # Provides only a bbox list, simulating an incomplete entry
        ("dav", {"title": "BBOX_Tile", "year": 2010, "bbox": [0, 0, 10, 10]}),
    ]

    hook = SpatialCullHook(sort_by="year", reverse=True)
    culled = hook.run(entries)

    # The BBOX tile should be successfully parsed, evaluated, and dropped because it is fully covered by WKB_Tile
    assert len(culled) == 1
    assert culled[0][1]["title"] == "WKB_Tile"


def test_hook_resolves_nested_metadata_keys():
    """
    Proves that a hook correctly extracts custom keys that FetchModule
    automatically tucks into the 'metadata' sub-dictionary during ingestion.
    """
    # 1. Instantiate a bare FetchModule
    mod = FetchModule(name="test_mod", use_cache=False)

    # 2. Add entries using the standard ingestion method.
    # 'custom_priority' is a non-standard key, so FetchModule will nest it.
    geom = box(0, 0, 10, 10)

    mod.add_entry_to_results(
        url="http://test.com/low.tif",
        dst_fn="low.tif",
        data_type="test",
        geometry=geom,
        date="2010",
        custom_priority=10,
    )
    mod.add_entry_to_results(
        url="http://test.com/high.tif",
        dst_fn="high.tif",
        data_type="test",
        date="2010",
        geometry=geom,
        custom_priority=99,
    )

    # Sanity check: Ensure the base module actually nested the key
    assert "date" not in mod.results[0]
    assert mod.results[0]["metadata"]["date"] == "2010"
    assert mod.results[0]["custom_priority"] == 10

    # 3. Format the payload exactly as the pipeline runner does
    hook_payload = [(mod, entry) for entry in mod.results]

    # 4. Execute the hook using the custom nested key
    hook = SpatialCullHook(sort_by="custom_priority", reverse=True, min_coverage=0.99)
    culled = hook.run(hook_payload)

    # 5. If the hook failed to check the metadata dict, get_sort_val would return ""
    # for both, and the stable sort would keep 'low.tif' instead of 'high.tif'.
    assert len(culled) == 1
    assert culled[0][1]["custom_priority"] == 99
