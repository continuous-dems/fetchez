"""Tests for dataset contribution identity."""

from copy import deepcopy

import pytest

from fetchez.entry import dataset_id


@pytest.fixture
def entry():
    return {
        "url": "https://example.org/survey.laz",
        "dst_fn": "survey.laz",
        "data_type": "lidar",
        "metadata": {"title": "Example survey"},
    }


def test_dataset_id_unchanged_without_modifiers(entry):
    """Existing dataset identities remain backward compatible."""
    assert dataset_id(entry) == entry["url"]


def test_dataset_id_kwargs_are_deterministic(entry):
    """Keyword argument ordering must not affect identity."""
    first = dataset_id(entry, weight=2.0, strategy="mixed")
    second = dataset_id(entry, strategy="mixed", weight=2.0)

    assert first == second
    assert first != dataset_id(entry)


def test_dataset_id_kwargs_distinguish_contributions(entry):
    """Different processing parameters produce different identities."""
    assert dataset_id(entry, weight=1.0) != dataset_id(entry, weight=2.0)

    assert dataset_id(entry, weight=2.0) == dataset_id(entry, weight=2.0)


def test_contribution_id_distinguishes_processed_sources(entry):
    """Hooks can identify distinct outputs from the same dataset."""
    original = dataset_id(entry)

    entry["contribution_id"] = {
        "stack_qc": "filtered-v1",
    }

    filtered = dataset_id(entry)

    assert filtered != original

    entry["contribution_id"]["stack_qc"] = "filtered-v2"
    assert dataset_id(entry) != filtered


def test_multiple_hooks_contribute_independently(entry):
    """Multiple hooks can contribute without overwriting one another."""
    entry["contribution_id"] = {}

    entry["contribution_id"]["vertical_transform"] = "mllw-v1"
    first = dataset_id(entry)

    entry["contribution_id"]["stack_qc"] = "qc-v2"
    second = dataset_id(entry)

    assert first != second
    assert entry["contribution_id"] == {
        "vertical_transform": "mllw-v1",
        "stack_qc": "qc-v2",
    }


def test_contribution_order_does_not_matter(entry):
    """Equivalent contribution mappings have identical identities."""
    a = deepcopy(entry)
    b = deepcopy(entry)

    a["contribution_id"] = {
        "stack_qc": "qc-v2",
        "vertical_transform": "mllw-v1",
    }

    b["contribution_id"] = {
        "vertical_transform": "mllw-v1",
        "stack_qc": "qc-v2",
    }

    assert dataset_id(a) == dataset_id(b)


def test_unrelated_metadata_does_not_change_dataset_id(entry):
    """Descriptive metadata is not part of contribution identity."""
    entry["contribution_id"] = {"stack_qc": "qc-v2"}
    original = dataset_id(entry, weight=2.0)

    entry["metadata"]["title"] = "Updated title"
    entry["metadata"]["reviewed"] = True
    entry["status"] = "processed"
    entry["artifacts"] = {"hillshade": "preview.tif"}

    assert dataset_id(entry, weight=2.0) == original


def test_kwargs_and_contribution_id_are_combined(entry):
    """Consumer settings and upstream contributions both affect identity."""
    entry["contribution_id"] = {"stack_qc": "qc-v1"}

    original = dataset_id(entry, weight=1.0)

    assert original != dataset_id(entry, weight=2.0)

    entry["contribution_id"]["stack_qc"] = "qc-v2"

    assert original != dataset_id(entry, weight=1.0)


def test_empty_contribution_id_preserves_original_identity(entry):
    """An empty contribution mapping should be equivalent to no mapping."""
    original = dataset_id(entry)

    entry["contribution_id"] = {}

    assert dataset_id(entry) == original


def test_contribution_id_does_not_mutate_entry(entry):
    """Generating identifiers must not alter entry contents."""
    entry["contribution_id"] = {"stack_qc": "qc-v1"}
    before = deepcopy(entry)

    dataset_id(entry, weight=2.0)

    assert entry == before


def test_contribution_id_rejects_unsupported_values(entry):
    entry["contribution_id"] = {
        "stack_qc": object(),
    }

    with pytest.raises((TypeError, ValueError)):
        dataset_id(entry)
