# test_utils.py

from fetchez import utils
import pytest


def test_or_utils():
    "Test the common *_or utilities"

    assert utils.str_or(1) == "1"
    assert utils.str_or(1.25) == "1.25"
    assert utils.str_or(None) is None

    assert utils.float_or(1) == 1.0
    assert utils.float_or("string") is None
    assert utils.float_or(None) is None

    assert utils.int_or(1.25) == 1
    assert utils.int_or("string") is None
    assert utils.int_or(None) is None


def test_inc_utils():
    "Test the str2inc functions, which convert strings into geographic units"

    assert utils.str2inc("1s") == 0.0002777777777777778
    assert utils.str2inc(1) == 1.0
    assert utils.str2inc("1m") == 0.016666666666666666
    assert utils.str2inc("1t") == pytest.approx(8.983152841195214e-06)
    assert utils.str2inc("1a") is None


def test_remove_glob():
    "Make sure remove_glob resolves to remove_glob2"

    assert utils.remove_glob == utils.remove_glob2
