# test_utils.py

from fetchez import utils


def test_or_utils():
    "Test the common *_or utilities"

    assert utils.str_or(1) == "1"
    assert utils.str_or(1.25) == "1.25"

    assert utils.float_or(1) == 1.0
    assert utils.int_or("string") is None

    assert utils.int_or(1.25) == 1
    assert utils.int_or("string") is None


def test_inc_utils():
    "Test the str2inc functions, which convert strings into geographic units"

    assert utils.str2inc("1s") == 0.0002777777777777778
    assert utils.str2inc(1) == 1.0
    assert utils.str2inc("1m") == 0.002777777777777778
    assert utils.str2inc("1t") == 8.98311174991017e-06
    assert utils.str2inc("1a") == 1.0


def test_remove_glob():
    "Make sure remove_glob resolves to remove_glob2"

    assert utils.remove_glob == utils.remove_glob2
