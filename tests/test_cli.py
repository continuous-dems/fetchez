import subprocess
import sys

# CMD will run Fetchez
CMD = [sys.executable, "-m", "fetchez.cli"]


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

    result = run_fetchez(["--modules"])
    assert result.returncode == 0
    assert "multibeam" in result.stdout
    assert "local" in result.stdout


def test_list_hooks():
    """Can we list hooks?"""

    result = run_fetchez(["--list-hooks"])
    assert result.returncode == 0
    assert "dryrun" in result.stdout
    assert "enrich" in result.stdout


def test_hook_info():
    """Does the hook-info flag work?"""

    result = run_fetchez(["--hook-info", "audit"])
    assert result.returncode == 0
    assert "Write a summary of all operations" in result.stdout


def test_dry_run_ipinfo():
    """ Run a simple module."""

    result = run_fetchez(["ipinfo:ip=8.8.8.8", "--hook", "dryrun"])
    assert result.returncode == 0
