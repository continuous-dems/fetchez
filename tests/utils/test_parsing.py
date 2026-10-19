# test_parsing.py

from pathlib import Path
from fetchez.utils import parse_hook_string, parse_source_string


def test_parse_hook_string_basic():
    """Test basic hook parsing without arguments."""

    res = parse_hook_string("unzip")
    assert res == {"name": "unzip"}


def test_parse_hook_string_args_and_types():
    """Test argument splitting and automatic type inference."""

    res = parse_hook_string("rq:threshold=10.5,mode=percent,strict=true,cores=4")

    assert res["name"] == "rq"
    assert res["args"]["threshold"] == 10.5  # Inferred float
    assert res["args"]["mode"] == "percent"  # Kept as string
    assert res["args"]["strict"] is True  # Inferred boolean
    assert res["args"]["cores"] == 4  # Inferred integer


def test_parse_hook_string_implicit_flags():
    """Test implicit boolean flags (no equals sign)."""

    res = parse_hook_string("my_hook:verbose,debug")
    assert res["name"] == "my_hook"
    assert res["args"]["verbose"] is True
    assert res["args"]["debug"] is True


def test_parse_source_string_basic():
    """Test standard module string with args."""

    res = parse_source_string("copernicus:datatype=3,weight=1.5")

    assert res["module"] == "copernicus"
    assert res["args"]["datatype"] == 3
    assert res["args"]["weight"] == 1.5
    assert res["hooks"] == []


def test_parse_source_string_chained_hooks():
    """Test the '+' syntax for chaining hooks to a source."""

    source_str = "mbdb:want_inf=false+rq:threshold=10+outlierz+stream_reproject:dst_srs=EPSG:3857"
    res = parse_source_string(source_str)

    assert res["module"] == "mbdb"
    assert res["args"]["want_inf"] is False
    assert len(res["hooks"]) == 3

    # Check the chained hooks
    assert res["hooks"][0] == {"name": "rq", "args": {"threshold": 10}}
    assert res["hooks"][1] == {"name": "outlierz"}
    assert res["hooks"][2] == {
        "name": "stream_reproject",
        "args": {"dst_srs": "EPSG:3857"},
    }


def test_parse_source_local_file_detection(tmp_path):
    """Test that existing local paths are auto-converted to 'file' or 'local_fs' modules."""

    # Create a dummy file in the pytest temporary directory
    dummy_file = tmp_path / "test_data.laz"
    dummy_file.touch()

    # Test File Detection
    res_file = parse_source_string(str(dummy_file))
    assert res_file["module"] == "file"
    assert Path(res_file["args"]["paths"]) == dummy_file.absolute()

    # Test Directory Detection
    res_dir = parse_source_string(str(tmp_path))
    assert res_dir["module"] == "local_fs"
    assert Path(res_dir["args"]["path"]) == tmp_path.absolute()
