import pytest

from fetchez.entry import (
    ENTRY_IDENTITY_KEYS,
    ENTRY_KEYS,
    ENTRY_RUNTIME_KEYS,
    REQUIRED_ENTRY_KEYS,
    canonical_entry_identity,
    entry_id,
    source_id,
    dataset_id,
    is_entry,
    validate_entry,
)


def make_entry(**overrides):
    entry = {
        "url": "https://example.com/data.tif",
        "dst_fn": "/tmp/data.tif",
        "data_type": "raster",
    }
    entry.update(overrides)
    return entry


# =============================================================================
# Entry contract
# =============================================================================


def test_entry_is_an_extensible_mapping():
    entry = make_entry()

    assert is_entry(entry)

    entry["custom_field"] = "custom"
    entry["application_metadata"] = {"foo": "bar"}

    assert entry["custom_field"] == "custom"
    assert entry["application_metadata"]["foo"] == "bar"


def test_non_mapping_is_not_entry():
    assert not is_entry(None)
    assert not is_entry([])
    assert not is_entry("entry")


@pytest.mark.parametrize("key", REQUIRED_ENTRY_KEYS)
def test_required_keys_are_standard_entry_keys(key):
    assert key in ENTRY_KEYS


def test_validate_entry_accepts_normal_entry():
    validate_entry(make_entry())


def test_validate_entry_rejects_missing_required_keys():
    with pytest.raises(ValueError, match="dst_fn"):
        validate_entry({"data_type": "raster"})

    with pytest.raises(ValueError, match="data_type"):
        validate_entry({"dst_fn": "/tmp/data.tif"})


def test_validate_entry_allows_partial_entry_when_requested():
    validate_entry({"url": "https://example.com/foo"}, require=False)


def test_validate_entry_rejects_non_mapping():
    with pytest.raises(TypeError):
        validate_entry("not an entry")


def test_validate_entry_requires_url():
    with pytest.raises(ValueError, match="url"):
        validate_entry(
            {
                "dst_fn": "/tmp/data.tif",
                "data_type": "raster",
            }
        )


def test_file_url_is_valid():
    validate_entry(
        {
            "url": "file:///tmp/data.tif",
            "dst_fn": "/tmp/data.tif",
            "data_type": "raster",
        }
    )


# =============================================================================
# Identity
# =============================================================================


def test_entry_id_is_deterministic():
    entry = make_entry()

    assert entry_id(entry) == entry_id(entry.copy())


def test_entry_id_is_independent_of_dict_order():
    first = {
        "url": "https://example.com/data.tif",
        "dst_fn": "/tmp/data.tif",
        "data_type": "raster",
        "profile": "generic-raster",
    }

    second = {
        "profile": "generic-raster",
        "data_type": "raster",
        "dst_fn": "/tmp/data.tif",
        "url": "https://example.com/data.tif",
    }

    assert entry_id(first) == entry_id(second)


def test_entry_id_changes_when_semantic_field_changes():
    entry = make_entry()
    original = entry_id(entry)

    entry["data_type"] = "vector"

    assert entry_id(entry) != original


def test_entry_id_changes_when_profile_changes():
    entry = make_entry(profile="generic-raster")
    original = entry_id(entry)

    entry["profile"] = "rasterio-point"

    assert entry_id(entry) != original


def test_entry_id_doesnt_change_when_destination_changes():
    entry = make_entry()
    original = entry_id(entry)

    entry["dst_fn"] = "/tmp/other.tif"

    assert entry_id(entry) == original


def test_entry_id_changes_when_data_type_changes():
    entry = make_entry()
    original = entry_id(entry)

    entry["data_type"] = "vector"

    assert entry_id(entry) != original


def test_entry_id_changes_when_metadata_changes():
    entry = make_entry(metadata={"resolution": "1m"})
    original = entry_id(entry)

    entry["metadata"]["resolution"] = "10m"

    assert entry_id(entry) != original


def test_runtime_state_does_not_change_entry_id():
    entry = make_entry()
    original = entry_id(entry)

    entry["status"] = 1
    entry["stream"] = object()
    entry["stream_type"] = "raster-stream"
    entry["artifacts"] = {"example": "/tmp/example.tif"}

    assert entry_id(entry) == original


def test_arbitrary_extension_keys_do_not_change_entry_id():
    entry = make_entry()
    original = entry_id(entry)

    entry["globato_specific"] = {
        "some_runtime_setting": 123,
    }

    assert entry_id(entry) == original


def test_identity_contains_only_declared_identity_fields():
    entry = make_entry(
        custom="ignored",
        status=1,
        artifacts={"foo": "bar"},
    )

    canonical = canonical_entry_identity(entry)

    for key in ENTRY_IDENTITY_KEYS:
        if key in entry:
            assert f'"{key}"' in canonical

    assert "custom" not in canonical
    assert "status" not in canonical
    assert "artifacts" not in canonical


def test_identity_does_not_depend_on_object_memory_address():
    entry1 = make_entry(custom_object=object())
    entry2 = make_entry(custom_object=object())

    # custom_object is intentionally outside ENTRY_IDENTITY_KEYS.
    assert entry_id(entry1) == entry_id(entry2)


def test_identity_key_sets_are_disjoint_where_expected():
    assert ENTRY_RUNTIME_KEYS.isdisjoint(ENTRY_IDENTITY_KEYS)


def test_source_id_uses_url():
    entry = make_entry(
        url="file:///data/foo.tif",
        dst_fn="/cache/foo.tif",
    )

    assert source_id(entry) == "file:///data/foo.tif"


def test_dataset_id_prefers_checksum():
    entry = make_entry(
        url="https://example.com/foo.tif",
        checksum="abc123",
    )

    assert dataset_id(entry) == "abc123"


def test_dataset_id_does_not_depend_on_materialization_path():
    one = make_entry(
        url="https://example.com/foo.tif",
        dst_fn="/cache/foo.tif",
    )
    two = make_entry(
        url="https://example.com/foo.tif",
        dst_fn="/scratch/foo.tif",
    )

    assert dataset_id(one) == dataset_id(two)
