"""Repository-native tests for fetchez.hooks.exec.Exec.

Place this file under tests/; requires the shared utility module at
fetchez/output.py and the Exec hook at fetchez/hooks/exec.py.
"""

import importlib
import sys

import pytest

Exec = importlib.import_module("fetchez.hooks.exec").Exec


def entry(path, status=0):
    return {"dst_fn": path, "status": status, "artifacts": {}}


def copy_cmd():
    return [
        sys.executable,
        "-c",
        'import pathlib,sys; pathlib.Path(sys.argv[2]).write_bytes(pathlib.Path(sys.argv[1]).read_bytes()+b"!")',
        "{file}",
        "{output}",
    ]


def test_legacy_side_effect(tmp_path):
    original = tmp_path / "input file.txt"
    original.write_text("a")
    item = entry(original)
    cmd = [
        sys.executable,
        "-c",
        'import sys; assert sys.argv[1].endswith("input file.txt")',
        "{file}",
    ]
    assert Exec(cmd=cmd).run([(None, item)])[0][1] is item
    assert item["dst_fn"] == original
    assert item["artifacts"] == {}


def test_transform_chain_and_spaces(tmp_path):
    source = tmp_path / "input file.txt"
    source.write_bytes(b"a")
    item = entry(source)
    hook = Exec(cmd=copy_cmd(), output={"suffix": "_first", "artifact_id": "first"})
    hook.run([(None, item)])
    first = item["dst_fn"]
    assert first.read_bytes() == b"a!"
    assert item["artifacts"]["first"] == first
    hook2 = Exec(cmd=copy_cmd(), output={"suffix": "_second", "artifact_id": "second"})
    hook2.run([(None, item)])
    assert item["dst_fn"].read_bytes() == b"a!!"
    assert item["artifacts"]["first"] == first


def test_multiple_entries(tmp_path):
    items = []
    for stem in ("a", "b"):
        p = tmp_path / (stem + ".txt")
        p.write_bytes(stem.encode())
        items.append((None, entry(p)))
    Exec(
        cmd=copy_cmd(),
        output={"output_path": str(tmp_path / "converted") + "/", "suffix": "_new"},
    ).run(items)
    assert [i["dst_fn"].read_bytes() for _, i in items] == [b"a!", b"b!"]


def test_command_failure_keeps_original(tmp_path):
    source = tmp_path / "original.txt"
    source.write_bytes(b"original")
    target = tmp_path / "original_processed.txt"
    target.write_bytes(b"prior")
    item = entry(source)
    failing = [sys.executable, "-c", "import sys; sys.exit(4)", "{file}", "{output}"]
    with pytest.raises(Exception) as _e:
        Exec(cmd=failing, output={}).run([(None, item)])
    assert item["dst_fn"] == source
    assert item["artifacts"] == {}
    assert target.read_bytes() == b"prior"


def test_missing_output_does_not_publish(tmp_path):
    source = tmp_path / "input.txt"
    source.write_bytes(b"input")
    item = entry(source)
    cmd = [sys.executable, "-c", "pass", "{output}"]
    with pytest.raises(FileNotFoundError):
        Exec(cmd=cmd, output={}).run([(None, item)])
    assert item["dst_fn"] == source
    assert not (tmp_path / "input_processed.txt").exists()


def test_output_opt_out(tmp_path):
    source = tmp_path / "input.txt"
    source.write_bytes(b"i")
    item = entry(source)
    Exec(cmd=copy_cmd(), output={"update_entry": False}).run([(None, item)])
    assert item["dst_fn"] == source
    assert item["artifacts"]["exec"].read_bytes() == b"i!"


def test_skip_failed_entries(tmp_path):
    item = entry(tmp_path / "absent.txt", status=-1)
    assert (
        Exec(cmd=[sys.executable, "-c", "raise AssertionError"]).run([(None, item)])[0][
            1
        ]
        is item
    )


def test_requires_output_placeholder(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("v")
    with pytest.raises(ValueError):
        Exec(cmd=[sys.executable, "-c", "pass"], output={}).run([(None, entry(source))])
