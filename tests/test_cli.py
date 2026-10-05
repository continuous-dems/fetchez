# test_cli.py
import pytest
import subprocess
import sys
import yaml

from fetchez.utils import parse_hook_string
from fetchez.cli import cli
from fetchez.cli.pipeline import organize_pipeline_commands

from click.testing import CliRunner

# Testing CLI using subprocess

# CMD will run Fetchez
CMD = [sys.executable, "-m", "fetchez.cli.__init__"]


@pytest.fixture
def runner():
    """Fixture to provide a Click CliRunner for all tests."""

    return CliRunner()


def run_fetchez(args):
    """Run fetchez and return result."""

    return subprocess.run(CMD + args, capture_output=True, text=True)


def test_help():
    """Does the help menu work?"""

    result = run_fetchez(["--help"])
    assert result.returncode == 0


def test_version():
    """Does version print?"""

    result = run_fetchez(["--version"])
    assert result.returncode == 0


def test_list_modules():
    """Can we list modules without crashing?"""

    result = run_fetchez(["modules", "list"])
    assert result.returncode == 0
    assert "multibeam" in result.stdout
    assert "local" in result.stdout


def test_list_hooks():
    """Can we list hooks?"""

    result = run_fetchez(["hooks", "list"])
    assert result.returncode == 0
    assert "dryrun" in result.stdout
    assert "enrich" in result.stdout


def test_hook_info():
    """Does the hook-info flag work?"""

    result = run_fetchez(["hooks", "info", "audit"])
    assert result.returncode == 0
    assert "Save a run summary of fetch entries to disk" in result.stdout


# this test randomly fails sometimes, due to network issues
# def test_dry_run_ipinfo():
#     """Run a simple module."""

#     result = run_fetchez(["run", "ipinfo", "--ip", "8.8.8.8", "--hook", "dryrun"])
#     assert result.returncode == 0


# test module string parsing in cli (no supported atm)
# def test_dry_run_ipinfo():
#     """Run a simple module."""

#     result = run_fetchez(["run", "ipinfo:ip=8.8.8.8", "--hook", "dryrun"])
#     assert result.returncode == 0


# Testing cli functions from python


def test_parse_hook_string_simple():
    """Test basic hook parsing with string arguments."""

    hook = parse_hook_string("reproject:crs=EPSG:3857")
    assert hook["name"] == "reproject"
    assert hook["args"] == {"crs": "EPSG:3857"}


def test_parse_hook_string_type_inference():
    """Test if the parser correctly identifies booleans and numbers."""

    hook = parse_hook_string("filter:match=.tif,force=true,retries=3")
    assert hook["name"] == "filter"
    assert hook["args"]["match"] == ".tif"
    assert hook["args"]["force"] is True
    assert hook["args"]["retries"] == 3


def test_parse_hook_string_no_args():
    """Test a hook string that has no arguments."""

    hook = parse_hook_string("unzip")
    assert hook["name"] == "unzip"
    assert hook.get("args") is None


def test_region_echo_bbox(runner):
    """Test the spatial parsing engine (No network required)."""

    result = runner.invoke(
        cli, ["regions", "echo", "-R", "-120/-119/34/35", "-F", "gmt"]
    )

    assert result.exit_code == 0
    assert "-120.0/-119.0/34.0/35.0" in result.output.strip()


def test_help_exposes_build_and_run():
    """Top-level help advertises the primary pipeline commands."""

    result = run_fetchez(["--help"])

    assert result.returncode == 0
    assert "build" in result.stdout
    assert "run" in result.stdout


def test_build_help():
    """Build is the ad-hoc pipeline construction command."""

    result = run_fetchez(["build", "--help"])

    assert result.returncode == 0
    assert "Build and optionally execute a pipeline" in result.stdout


def test_run_help():
    """Run executes registered or local recipes."""

    result = run_fetchez(["run", "--help"])

    assert result.returncode == 0
    assert "Execute a Fetchez recipe" in result.stdout
    assert "registered recipe" in result.stdout
    assert "local YAML recipe" in result.stdout


def test_recipes_help_is_discovery_only():
    result = run_fetchez(["recipes", "--help"])

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "info" in result.stdout
    assert "validate" in result.stdout
    assert "run" not in result.stdout


def test_build_export(runner, tmp_path):
    """Build can construct and export a recipe without executing it."""

    output = tmp_path / "pipeline.yaml"

    result = runner.invoke(
        cli,
        [
            "build",
            "--export",
            str(output),
            "dav",
            "--datatype",
            "raster",
        ],
    )

    assert result.exit_code == 0
    assert output.exists()

    config = yaml.safe_load(output.read_text())

    assert config["modules"][0]["module"] == "dav"
    assert config["modules"][0]["args"]["datatype"] == "raster"


def test_dynamic_module_help_uses_cli_metadata(runner):
    result = runner.invoke(cli, ["build", "dav", "--help"])

    assert result.exit_code == 0
    assert "NOAA Digital Coast (Data Access Viewer)" in result.output
    assert "Data type:" in result.output


# def test_build_bundle_select(runner, tmp_path):
#     output = tmp_path / "bundle.yaml"

#     result = runner.invoke(
#         cli,
#         [
#             "build",
#             "--export",
#             str(output),
#             "test-bundle",
#             "--select",
#             "products=1m/1_9as",
#         ],
#     )

#     assert result.exit_code == 0

#     config = yaml.safe_load(output.read_text())
#     bundle = config["modules"][0]

#     assert bundle["select"]["products"] == ["1m", "1_9as"]


def test_hooks_before_first_module_are_global():
    commands = [
        {"type": "hook", "name": "audit"},
        {"type": "module", "module": "tnm", "args": {}},
    ]

    modules, globals_ = organize_pipeline_commands(commands)

    assert globals_ == [{"name": "audit"}]
    assert modules == [
        {"module": "tnm", "args": {}},
    ]


def test_hooks_after_module_attach_to_module():
    commands = [
        {"type": "module", "module": "tnm", "args": {}},
        {"type": "hook", "name": "audit"},
        {"type": "hook", "name": "checksum"},
    ]

    modules, globals_ = organize_pipeline_commands(commands)

    assert globals_ == []
    assert modules[0]["hooks"] == [
        {"name": "audit"},
        {"name": "checksum"},
    ]


def test_hooks_after_bundle_become_append_hooks():
    commands = [
        {"type": "module", "bundle": "glob-tnm", "args": {}},
        {"type": "hook", "name": "audit"},
    ]

    modules, globals_ = organize_pipeline_commands(commands)

    assert globals_ == []
    assert modules[0]["append_hooks"] == [
        {"name": "audit"},
    ]


def test_preset_scope_follows_position():
    commands = [
        {"type": "preset", "preset": "audit-full"},
        {"type": "module", "module": "tnm", "args": {}},
        {"type": "preset", "preset": "raster-standard"},
    ]

    modules, globals_ = organize_pipeline_commands(commands)

    assert globals_ == [
        {"preset": "audit-full"},
    ]

    assert modules[0]["hooks"] == [
        {"preset": "raster-standard"},
    ]
