import pytest

from fetchez.modules.dav import DAV
from fetchez.modules.local_fs import LocalFS


@pytest.fixture
def module():
    return LocalFS()


def test_module_id_is_deterministic(module):
    assert module.module_id() == module.module_id()


def test_module_id_is_independent_of_runtime_state(module):
    original = module.module_id()

    module.status = 1
    module.results = [{"anything": "here"}]
    module.use_cache = False

    assert module.module_id() == original


def test_module_id_changes_with_configuration(module):
    original = module.module_id()

    module.params["example"] = "changed"

    assert module.module_id() != original


def test_module_id_is_independent_of_dict_order():
    class_a = {
        "url": "https://example.com/foo",
        "product": "test",
        "weight": 1,
    }

    class_b = {
        "weight": 1,
        "product": "test",
        "url": "https://example.com/foo",
    }

    # Via the same concrete module class.
    assert LocalFS.module_id_from_kwargs(**class_a) == LocalFS.module_id_from_kwargs(
        **class_b
    )


def test_module_id_distinguishes_module_classes():
    assert LocalFS.module_id_from_kwargs(url="x") != DAV.module_id_from_kwargs(url="x")


def test_datatype_aliases_produce_same_id():
    assert LocalFS.module_id_from_kwargs(
        datatype="raster"
    ) == LocalFS.module_id_from_kwargs(data_type="raster")


def test_config_and_instance_have_same_module_id():
    args = {
        "product": "test",
        "weight": 2.0,
    }

    module = LocalFS(**args)

    assert module.module_id() == LocalFS.module_id_from_kwargs(**args)


def test_explicit_defaults_do_not_change_module_id():
    assert LocalFS.module_id_from_kwargs(
        product="test", weight=2.0
    ) == LocalFS.module_id_from_kwargs(
        product="test",
        weight=2.0,
        min_year=None,
        max_year=None,
        uncertainty=0.0,
        params={},
    )


def test_instance_config_matches_raw_config():
    args = {
        "product": "test",
        "weight": 2.0,
    }

    module = LocalFS(**args)

    assert module.canonical_module_config() == (
        LocalFS.canonical_module_config_from_kwargs(**args)
    )


def test_module_name_is_part_of_canonical_config():
    config = LocalFS.canonical_module_config_from_kwargs(
        product="test",
        weight=2.0,
    )

    assert config["name"] == LocalFS.name


def test_subclass_explicit_defaults_do_not_change_module_id():
    assert LocalFS.module_id_from_kwargs(
        product="test"
    ) == LocalFS.module_id_from_kwargs(
        product="test",
        path=None,
        paths=None,
        ext=".tif",
        datatype=None,
        data_type=None,
        want_inf=False,
    )
