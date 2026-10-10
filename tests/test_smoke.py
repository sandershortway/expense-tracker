import sys


def test_python_version_floor() -> None:
    assert sys.version_info >= (3, 15)
