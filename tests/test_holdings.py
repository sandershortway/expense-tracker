from decimal import Decimal

from investment_ledger.domain import StoredTransaction, TransactionData
from investment_ledger.holdings import compute_holdings


def stored(entry_order, **overrides):
    values = {
        "side": "buy",
        "instrument_type": "stock",
        "ticker": "ACME",
        "exchange": "XNAS",
        "trade_date": "2024-01-02",
        "quantity": "2.5",
        "unit_price_eur": "4.00",
        "gross_amount_eur": "10.00",
        "fee_eur": None,
        "name": "Acme Corp",
    }
    values.update(overrides)
    return StoredTransaction(
        transaction_id=f"tx-{entry_order}",
        entry_order=entry_order,
        data=TransactionData.from_mapping(values),
        created_at="2024-01-02T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
    )


def position_for(report, ticker="ACME", exchange="XNAS"):
    matches = [
        p
        for p in report.positions
        if p.ticker == ticker and p.exchange == exchange
    ]
    assert len(matches) == 1
    return matches[0]


def test_empty_ledger_produces_empty_report():
    report = compute_holdings([])
    assert report.positions == []
    assert report.to_mapping() == {
        "count": 0,
        "holdings": [],
        "totals": {
            "cost_basis_eur": "0.00",
            "total_invested_eur": "0.00",
            "total_proceeds_eur": "0.00",
            "realized_pnl_eur": "0.00",
            "total_fees_eur": "0.00",
        },
    }


def test_single_buy_capitalizes_fee_into_cost_basis():
    report = compute_holdings(
        [stored(1, quantity="2.5", gross_amount_eur="10.00", fee_eur="0.50")]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("2.5")
    assert position.cost_basis_eur == Decimal("10.50")
    assert position.total_fees_eur == Decimal("0.50")
    assert position.realized_pnl_eur == Decimal("0")
    assert position.transaction_count == 1
    assert position.first_trade_date.isoformat() == "2024-01-02"
    assert position.average_cost_eur == Decimal("4.2")
    mapping = position.to_mapping()
    assert mapping["cost_basis_eur"] == "10.50"
    assert mapping["average_cost_eur"] == "4.200000"


def test_multiple_buys_accumulate_quantity_and_average_cost():
    report = compute_holdings(
        [
            stored(
                1,
                quantity="10",
                unit_price_eur="10.00",
                gross_amount_eur="100.00",
                fee_eur="5.00",
            ),
            stored(
                2,
                trade_date="2024-02-01",
                quantity="10",
                unit_price_eur="20.00",
                gross_amount_eur="200.00",
                fee_eur="5.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("20")
    assert position.cost_basis_eur == Decimal("310")
    assert position.average_cost_eur == Decimal("15.5")
    assert position.total_invested_eur == Decimal("310")
    assert position.first_trade_date.isoformat() == "2024-01-02"
    assert position.last_trade_date.isoformat() == "2024-02-01"


def test_partial_sell_releases_proportional_cost_and_realizes_pnl():
    report = compute_holdings(
        [
            stored(
                1,
                quantity="10",
                unit_price_eur="100.00",
                gross_amount_eur="1000.00",
                fee_eur="5.00",
            ),
            stored(
                2,
                trade_date="2024-02-01",
                side="sell",
                quantity="5",
                unit_price_eur="120.00",
                gross_amount_eur="600.00",
                fee_eur="2.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("5")
    assert position.cost_basis_eur == Decimal("502.50")
    assert position.total_proceeds_eur == Decimal("598.00")
    assert position.realized_pnl_eur == Decimal("95.50")
    assert position.average_cost_eur == Decimal("100.5")
    assert position.warnings == []


def test_full_sell_keeps_closed_position_with_realized_pnl():
    report = compute_holdings(
        [
            stored(
                1,
                quantity="10",
                unit_price_eur="100.00",
                gross_amount_eur="1000.00",
                fee_eur="5.00",
            ),
            stored(
                2,
                trade_date="2024-02-01",
                side="sell",
                quantity="10",
                unit_price_eur="120.00",
                gross_amount_eur="1200.00",
                fee_eur="5.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("0")
    assert position.cost_basis_eur == Decimal("0")
    assert position.average_cost_eur is None
    assert position.realized_pnl_eur == Decimal("190.00")
    assert position.to_mapping()["average_cost_eur"] is None
    assert position.warnings == []


def test_oversell_warns_and_continues_with_negative_quantity():
    report = compute_holdings(
        [
            stored(
                1,
                quantity="5",
                unit_price_eur="100.00",
                gross_amount_eur="500.00",
            ),
            stored(
                2,
                trade_date="2024-02-01",
                side="sell",
                quantity="8",
                unit_price_eur="110.00",
                gross_amount_eur="880.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("-3")
    assert position.cost_basis_eur == Decimal("0")
    assert position.realized_pnl_eur == Decimal("380")
    assert len(position.warnings) == 1
    assert "3" in position.warnings[0]
    assert position.to_mapping()["warnings"]


def test_sell_without_holding_warns():
    report = compute_holdings(
        [
            stored(
                1,
                side="sell",
                quantity="2",
                unit_price_eur="50.00",
                gross_amount_eur="100.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("-2")
    assert len(position.warnings) == 1


def test_groups_by_ticker_and_exchange_separately():
    report = compute_holdings(
        [
            stored(1, quantity="1", gross_amount_eur="4.00"),
            stored(
                2,
                ticker="ACME",
                exchange="XLON",
                quantity="3",
                unit_price_eur="4.00",
                gross_amount_eur="12.00",
            ),
            stored(
                3,
                ticker="BETA",
                quantity="2",
                unit_price_eur="4.00",
                gross_amount_eur="8.00",
                instrument_type="etf",
                name="Beta ETF",
            ),
        ]
    )
    assert [p.ticker for p in report.positions] == ["ACME", "ACME", "BETA"]
    xnas = position_for(report, "ACME", "XNAS")
    xlon = position_for(report, "ACME", "XLON")
    beta = position_for(report, "BETA")
    assert xnas.net_quantity == Decimal("1")
    assert xlon.net_quantity == Decimal("3")
    assert beta.instrument_type == "etf"
    assert beta.name == "Beta ETF"


def test_out_of_order_entries_fold_in_trade_date_order():
    report = compute_holdings(
        [
            stored(
                1,
                trade_date="2024-02-01",
                side="sell",
                quantity="5",
                unit_price_eur="120.00",
                gross_amount_eur="600.00",
            ),
            stored(
                2,
                trade_date="2024-01-02",
                quantity="10",
                unit_price_eur="100.00",
                gross_amount_eur="1000.00",
            ),
        ]
    )
    position = position_for(report)
    assert position.net_quantity == Decimal("5")
    assert position.warnings == []


def test_totals_sum_across_positions():
    report = compute_holdings(
        [
            stored(
                1,
                quantity="10",
                unit_price_eur="10.00",
                gross_amount_eur="100.00",
                fee_eur="5.00",
            ),
            stored(
                2,
                ticker="BETA",
                instrument_type="etf",
                quantity="4",
                unit_price_eur="50.00",
                gross_amount_eur="200.00",
                fee_eur="10.00",
            ),
            stored(
                3,
                trade_date="2024-02-01",
                side="sell",
                quantity="5",
                unit_price_eur="12.00",
                gross_amount_eur="60.00",
            ),
        ]
    )
    totals = report.totals()
    assert totals["cost_basis_eur"] == Decimal("262.50")
    assert totals["total_invested_eur"] == Decimal("315")
    assert totals["total_proceeds_eur"] == Decimal("60")
    assert totals["realized_pnl_eur"] == Decimal("7.50")
    assert totals["total_fees_eur"] == Decimal("15")
    assert report.to_mapping()["totals"]["cost_basis_eur"] == "262.50"


def test_real_purchase_batch_matches_expected_positions():
    report = compute_holdings(
        [
            stored(
                1,
                ticker="NVDA",
                name="Nvidia",
                trade_date="2025-03-11",
                quantity="1.03284445",
                unit_price_eur="96.82",
                gross_amount_eur="100.00",
                fee_eur="0.00",
            ),
            stored(
                2,
                ticker="NVDA",
                name="Nvidia",
                trade_date="2025-12-05",
                quantity="3.07180340",
                unit_price_eur="156.26",
                gross_amount_eur="480.00",
                fee_eur="4.75",
            ),
            stored(
                3,
                ticker="NVDA",
                name="Nvidia",
                trade_date="2026-03-28",
                quantity="6.86153424",
                unit_price_eur="145.74",
                gross_amount_eur="1000.00",
                fee_eur="9.90",
            ),
            stored(
                4,
                ticker="SXRV",
                instrument_type="etf",
                name="S&P 500 Technology",
                trade_date="2026-04-23",
                quantity="52.50721974",
                unit_price_eur="38.09",
                gross_amount_eur="2000.00",
                fee_eur="19.80",
            ),
        ]
    )
    nvda = position_for(report, "NVDA", "XNAS")
    sxrv = position_for(report, "SXRV")
    assert nvda.net_quantity == Decimal("10.96618209")
    assert nvda.to_mapping()["cost_basis_eur"] == "1594.65"
    assert nvda.name == "Nvidia"
    assert sxrv.net_quantity == Decimal("52.50721974")
    assert sxrv.to_mapping()["cost_basis_eur"] == "2019.80"
    assert sxrv.instrument_type == "etf"
    totals = report.to_mapping()["totals"]
    assert totals["cost_basis_eur"] == "3614.45"
    assert totals["total_fees_eur"] == "34.45"
    assert totals["realized_pnl_eur"] == "0.00"
