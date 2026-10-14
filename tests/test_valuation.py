import json
from decimal import Decimal

import pytest

from investment_ledger.domain import StoredTransaction, TransactionData
from investment_ledger.holdings import compute_holdings
from investment_ledger.valuation import (
    Price,
    PriceFileError,
    load_prices,
    portfolio_return,
    value_position,
)


def stored(entry_order, **overrides):
    values = {
        "side": "buy",
        "instrument_type": "etf",
        "ticker": "AEX",
        "exchange": "XAMS",
        "trade_date": "2025-01-02",
        "quantity": "10",
        "unit_price_eur": "100.00",
        "gross_amount_eur": "1000.00",
        "fee_eur": "10.00",
    }
    values.update(overrides)
    return StoredTransaction(
        f"tx-{entry_order}",
        entry_order,
        TransactionData.from_mapping(values),
        "2025-01-02T00:00:00Z",
        "2025-01-02T00:00:00Z",
    )


def price(value):
    return Price(Decimal(value), "2026-10-14", "test")


def test_open_position_market_value_and_total_return():
    position = compute_holdings([stored(1)]).positions[0]

    valuation = value_position(position, {"AEX@XAMS": price("121.20")})

    assert valuation.market_value_eur == Decimal("1212.00")
    assert valuation.unrealized_pnl_eur == Decimal("202.00")
    assert valuation.total_return_pct == Decimal("20.00")


def test_total_return_includes_sale_proceeds():
    position = compute_holdings(
        [
            stored(1),
            stored(
                2,
                side="sell",
                trade_date="2025-02-01",
                quantity="5",
                unit_price_eur="110.00",
                gross_amount_eur="550.00",
                fee_eur="5.00",
            ),
        ]
    ).positions[0]

    valuation = value_position(position, {"AEX@XAMS": price("120.00")})

    assert valuation.market_value_eur == Decimal("600.00")
    assert valuation.unrealized_pnl_eur == Decimal("95.00")
    assert valuation.total_return_pct == Decimal("13.37")


def test_unpriced_position_has_no_valuation_and_no_portfolio_total():
    positions = compute_holdings([stored(1)]).positions
    valuations = [value_position(p, {}) for p in positions]

    assert valuations[0].market_value_eur is None
    assert portfolio_return(positions, valuations) == (None, None)


def test_closed_position_does_not_need_a_price_for_portfolio_total():
    positions = compute_holdings(
        [
            stored(1),
            stored(
                2,
                side="sell",
                trade_date="2025-02-01",
                unit_price_eur="110.00",
                gross_amount_eur="1100.00",
                fee_eur="0.00",
            ),
            stored(3, ticker="NVD", exchange="XETRA"),
        ]
    ).positions
    valuations = [
        value_position(p, {"NVD@XETRA": price("110.00")}) for p in positions
    ]

    market_value, total = portfolio_return(positions, valuations)

    assert market_value == Decimal("1100.00")
    assert total == Decimal("8.91")


def test_load_prices_normalizes_keys_and_handles_missing_file(tmp_path):
    assert load_prices(tmp_path / "missing.json") == {}
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "prices": {
                    "aex@xams": {
                        "price_eur": "113.66",
                        "as_of": "2026-10-14",
                        "source": "example",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    prices = load_prices(path)

    assert prices["AEX@XAMS"].price_eur == Decimal("113.66")


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"prices": []},
        {"prices": {"AEX@XAMS": {"price_eur": 113.66}}},
        {"prices": {"AEX@XAMS": {"price_eur": "abc"}}},
        {"prices": {"AEX@XAMS": {"price_eur": "0"}}},
    ],
)
def test_load_prices_rejects_invalid_files(tmp_path, document):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(PriceFileError):
        load_prices(path)
