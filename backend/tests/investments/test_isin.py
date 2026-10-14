import pytest

from findash.investments.isin import is_valid_isin


@pytest.mark.parametrize(
    "isin",
    [
        "US0378331005",
        "US67066G1040",
        "NL0010273215",
        "IE00B5BMR087",
        "IE00B0M62Y33",
        "IE00BGV5VN51",
        "IE00B3WJKG14",
        "FR0010717090",
    ],
)
def test_accepts_valid_isins(isin: str) -> None:
    assert is_valid_isin(isin)


@pytest.mark.parametrize(
    "isin",
    [
        "US0378331006",
        "NL0010273216",
        "US037833100",
        "US03783310055",
        "",
        "us0378331005",
        "U10378331005",
        "US037833100-",
        "US037833100A",
        " US0378331005",
    ],
)
def test_rejects_invalid_isins(isin: str) -> None:
    assert not is_valid_isin(isin)
