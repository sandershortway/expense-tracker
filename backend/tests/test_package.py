import importlib

import pytest


@pytest.mark.parametrize(
    "module", ["findash", "findash.core", "findash.investments"]
)
def test_package_modules_import(module: str) -> None:
    assert importlib.import_module(module).__doc__
