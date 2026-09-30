import pytest

from fetchez.registry import DataTypeRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """Start each test with a clean DataTypeRegistry."""
    DataTypeRegistry.reload_all()
    yield
    DataTypeRegistry.reload_all()


def test_builtin_data_types_are_registered():
    registry = DataTypeRegistry.get_registry()

    assert "archive" in registry
    assert "raster" in registry
    assert "vector" in registry


@pytest.mark.parametrize(
    "name",
    [
        "archive",
        "raster",
        "vector",
    ],
)
def test_builtin_data_type_exists(name):
    assert DataTypeRegistry.exists(name)


def test_unknown_data_type_does_not_exist():
    assert not DataTypeRegistry.exists("not-a-real-data-type")


def test_get_yaml_returns_data_type_definition():
    data_type = DataTypeRegistry.get_yaml("raster")

    assert data_type is not None
    assert data_type["name"] == "raster"
    assert data_type["description"] == "Raster dataset"
    assert data_type["category"] == "geospatial"


def test_get_yaml_returns_none_for_unknown_data_type():
    assert DataTypeRegistry.get_yaml("not-a-real-data-type") is None


def test_get_yaml_returns_independent_copy():
    first = DataTypeRegistry.get_yaml("raster")
    second = DataTypeRegistry.get_yaml("raster")

    assert first == second
    assert first is not second

    first["description"] = "modified"

    assert second["description"] == "Raster dataset"
    assert DataTypeRegistry.get_yaml("raster")["description"] == "Raster dataset"


def test_list_all_contains_builtin_data_types():
    data_types = DataTypeRegistry.load_all()

    assert "archive" in data_types
    assert "raster" in data_types
    assert "vector" in data_types


def test_data_type_registry_definitions_have_required_fields():
    for name, definition in DataTypeRegistry.load_all().items():
        assert definition["name"] == name
        assert definition.get("description")
        assert definition.get("category")


def test_data_type_registry_is_dynamic():
    registry = DataTypeRegistry.get_registry()

    registry["test-data-type"] = {
        "name": "test-data-type",
        "description": "Temporary test data type",
        "category": "test",
    }

    assert DataTypeRegistry.exists("test-data-type")
    assert (
        DataTypeRegistry.get_yaml("test-data-type")["description"]
        == "Temporary test data type"
    )


def test_reload_removes_runtime_registry_entries():
    registry = DataTypeRegistry.get_registry()

    registry["test-data-type"] = {
        "name": "test-data-type",
        "description": "Temporary test data type",
        "category": "test",
    }

    assert DataTypeRegistry.exists("test-data-type")

    DataTypeRegistry.reload_all()

    assert not DataTypeRegistry.exists("test-data-type")


def test_custom_yaml_data_type_can_be_registered():
    yaml_content = """
name: weather-grid
description: Weather grid data
category: geospatial
"""

    DataTypeRegistry._register_yaml(
        "test-provider",
        yaml_content,
        "weather-grid.yaml",
    )

    definition = DataTypeRegistry.get_yaml("weather-grid")

    assert definition is not None
    assert definition["name"] == "weather-grid"
    assert definition["description"] == "Weather grid data"
    assert definition["category"] == "geospatial"
    assert definition["provider"] == "test-provider"


def test_exists_is_case_sensitive():
    assert DataTypeRegistry.exists("raster")
    assert not DataTypeRegistry.exists("Raster")
