import pytest
from fetchez.utils import output_name, atomic_output


def test_names(tmp_path):
    entry = {"dst_fn": str(tmp_path / "scene.tif")}
    assert output_name(entry, suffix="_crop") == tmp_path / "scene_crop.tif"
    assert output_name(entry, extension=".nc") == tmp_path / "scene_processed.nc"
    assert (
        output_name(entry, output_path=str(tmp_path / "results") + "/")
        == tmp_path / "results/scene_processed.tif"
    )
    assert (
        output_name(
            entry, output_path=str(tmp_path / "{stem}_{index}.tif"), total=2, index=1
        )
        == tmp_path / "scene_1.tif"
    )
    with pytest.raises(ValueError):
        output_name(entry, output_path=str(tmp_path / "shared.tif"), total=2)
    with pytest.raises(ValueError):
        output_name(entry, output_path="{invalid}.tif")


def test_atomic_success(tmp_path):
    target = tmp_path / "out.tif"
    with atomic_output(target) as tmp:
        assert tmp.parent == target.parent
        assert tmp.suffix == ".tif"
        tmp.write_bytes(b"new")
        assert not target.exists()
    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_failure_preserves_previous(tmp_path):
    target = tmp_path / "out.tif"
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError):
        with atomic_output(target) as tmp:
            tmp.write_bytes(b"new")
            raise RuntimeError("failed")
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_no_overwrite(tmp_path):
    target = tmp_path / "out.tif"
    target.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        with atomic_output(target, overwrite=False):
            pass
