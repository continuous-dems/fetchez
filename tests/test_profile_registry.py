"""Tests for registered and inline reader profile resolution."""

import copy

import pytest

from fetchez.registry import ProfileRegistry

ProfileRegistry.load_all()


@pytest.fixture
def sample_profile():
    return {
        "name": "test-profile",
        "data_type": "raster",
        "reader": {
            "name": "test-reader",
            "args": {
                "band": 1,
                "chunk_size": 512,
            },
        },
    }


@pytest.fixture
def registered_profile(monkeypatch, sample_profile):
    """Provide an isolated profile registry for each test."""
    registry = {
        "test-profile": copy.deepcopy(sample_profile),
    }

    monkeypatch.setattr(
        ProfileRegistry,
        "_registry",
        registry,
    )
    monkeypatch.setattr(
        ProfileRegistry,
        "_loaded_registry",
        registry,
    )

    return registry


def test_resolve_registered_profile(registered_profile):
    profile = ProfileRegistry.resolve("test-profile")

    assert profile["name"] == "test-profile"
    assert profile["data_type"] == "raster"
    assert profile["reader"]["name"] == "test-reader"
    assert profile["reader"]["args"]["band"] == 1


def test_resolve_inline_profile(sample_profile):
    profile = ProfileRegistry.resolve(sample_profile)

    assert profile == sample_profile
    assert profile is not sample_profile


def test_resolve_registered_profile_returns_copy(registered_profile):
    first = ProfileRegistry.resolve("test-profile")
    second = ProfileRegistry.resolve("test-profile")

    first["reader"]["args"]["band"] = 3

    assert second["reader"]["args"]["band"] == 1
    assert registered_profile["test-profile"]["reader"]["args"]["band"] == 1


def test_resolve_inline_profile_returns_deep_copy(sample_profile):
    resolved = ProfileRegistry.resolve(sample_profile)

    resolved["reader"]["args"]["band"] = 5

    assert sample_profile["reader"]["args"]["band"] == 1


def test_resolve_overrides_registered_profile(registered_profile):
    profile = ProfileRegistry.resolve(
        "test-profile",
        overrides={
            "band": 2,
            "chunk_size": 1024,
        },
    )

    assert profile["reader"]["args"] == {
        "band": 2,
        "chunk_size": 1024,
    }

    # The registry's original definition remains unchanged.
    assert registered_profile["test-profile"]["reader"]["args"] == {
        "band": 1,
        "chunk_size": 512,
    }


def test_resolve_overrides_inline_profile(sample_profile):
    profile = ProfileRegistry.resolve(
        sample_profile,
        overrides={"band": 3},
    )

    assert profile["reader"]["args"]["band"] == 3
    assert profile["reader"]["args"]["chunk_size"] == 512

    assert sample_profile["reader"]["args"]["band"] == 1


def test_resolve_preserves_other_profile_metadata(
    registered_profile,
):
    profile = ProfileRegistry.resolve(
        "test-profile",
        overrides={"band": 2},
    )

    assert profile["name"] == "test-profile"
    assert profile["data_type"] == "raster"
    assert profile["reader"]["name"] == "test-reader"


def test_resolve_unknown_profile(registered_profile):
    assert ProfileRegistry.resolve("not-registered") is None


@pytest.mark.parametrize(
    "invalid",
    [None, 123, [], True],
)
def test_resolve_invalid_input(invalid):
    assert ProfileRegistry.resolve(invalid) is None


def test_resolve_overrides_create_missing_args():
    inline = {
        "reader": {
            "name": "test-reader",
        },
    }

    resolved = ProfileRegistry.resolve(
        inline,
        overrides={"band": 2},
    )

    assert resolved["reader"]["args"] == {"band": 2}
    assert "args" not in inline["reader"]


def test_resolve_independent_invocations(registered_profile):
    first = ProfileRegistry.resolve(
        "test-profile",
        overrides={"band": 1},
    )

    second = ProfileRegistry.resolve(
        "test-profile",
        overrides={"band": 3},
    )

    assert first["reader"]["args"]["band"] == 1
    assert second["reader"]["args"]["band"] == 3

    assert registered_profile["test-profile"]["reader"]["args"]["band"] == 1


def test_resolve_deep_copies_nested_reader_args():
    original = {
        "reader": {
            "name": "test-reader",
            "args": {
                "bands": [1, 2, 3],
                "options": {"masked": True},
            },
        },
    }

    resolved = ProfileRegistry.resolve(original)

    resolved["reader"]["args"]["bands"].append(4)
    resolved["reader"]["args"]["options"]["masked"] = False

    assert original["reader"]["args"]["bands"] == [1, 2, 3]
    assert original["reader"]["args"]["options"]["masked"] is True


@pytest.mark.parametrize(
    "invalid_profile",
    [
        {},
        {"reader": {}},
        {"reader": {"args": {"band": 1}}},
        {"reader": "test-reader"},
    ],
)
def test_resolve_rejects_malformed_inline_profiles(invalid_profile):
    assert ProfileRegistry.resolve(invalid_profile) is None
