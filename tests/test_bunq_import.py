from datetime import date, timedelta
from decimal import Decimal

import pytest

from investment_ledger.bunq_import import (
    BunqImportError,
    InstrumentMapping,
    parse_bunq_export,
)


def order(**overrides):
    values = {
        "entry_id": "bunq-001",
        "order_id": None,
        "asset": "AEX",
        "name": "AEX Short Name",
        "legal_name": "iShares AEX UCITS ETF",
        "isin": "IE00B0M62Y33",
        "side": "buy",
        "status": "completed",
        "date_local": "2025-03-11T08:31:00",
        "timezone": None,
        "quantity": "1.09",
        "unit_price": "91.52",
        "currency": "EUR",
        "fees": "0.00",
        "total": "100.00",
        "source_url": "https://example.invalid/orders/bunq-001",
    }
    values.update(overrides)
    return values


def export(*orders):
    return {
        "schema_version": "1.0",
        "export_date": "2026-10-14",
        "source": "synthetic fixture",
        "coverage": {"order_count": len(orders)},
        "orders": list(orders),
    }


def mapping(isin="IE00B0M62Y33", **overrides):
    fields = {"instrument_type": "etf", "ticker": "AEX", "exchange": "XAMS"}
    fields.update(overrides)
    return InstrumentMapping.from_values(**fields)


def test_uses_asset_name_when_optional_name_is_missing():
    source = order()
    del source["name"]
    parsed = parse_bunq_export(export(source))
    transactions, _ = parsed.transactions({"IE00B0M62Y33": mapping()})
    assert transactions[0]["name"] == "AEX"


def test_parse_buy_calculates_gross_from_displayed_quantity_and_price():
    parsed = parse_bunq_export(export(order()))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert parsed.isins == ("IE00B0M62Y33",)
    assert transactions == [
        {
            "side": "buy",
            "instrument_type": "etf",
            "ticker": "AEX",
            "exchange": "XAMS",
            "trade_date": "2025-03-11",
            "quantity": "1.09",
            "unit_price_eur": "91.52",
            "gross_amount_eur": "99.76",
            "fee_eur": "0.00",
            "currency": "EUR",
            "name": "AEX Short Name",
        }
    ]
    assert reports[0]["status"] == "ready"
    assert reports[0]["calculated_total_eur"] == "99.76"
    assert reports[0]["difference_eur"] == "-0.24"
    assert reports[0]["warnings"]


def test_sell_and_buy_rows_preserve_input_order_and_distinct_entry_ids():
    buy = order(entry_id="buy-1")
    sell = order(
        entry_id="sell-2",
        side="sell",
        date_local="2025-03-12T09:15:00",
        quantity="0.50",
        unit_price="100.00",
        fees="1.00",
        total="49.00",
    )
    parsed = parse_bunq_export(export(buy, sell))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert [row["side"] for row in transactions] == ["buy", "sell"]
    assert [row["gross_amount_eur"] for row in transactions] == [
        "99.76",
        "50.00",
    ]
    assert [report["entry_id"] for report in reports] == ["buy-1", "sell-2"]
    assert reports[0]["status"] == reports[1]["status"] == "ready"


def test_date_uses_local_date_without_timezone_conversion():
    source = order(
        date_local="2025-03-11T23:45:00-07:00", timezone="America/Los_Angeles"
    )
    parsed = parse_bunq_export(export(source))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert transactions[0]["trade_date"] == "2025-03-11"
    assert reports[0]["source"]["date_local"] == source["date_local"]
    assert reports[0]["source"]["timezone"] == "America/Los_Angeles"


def test_reports_zero_difference_without_warning():
    parsed = parse_bunq_export(
        export(
            order(quantity="1", unit_price="10.00", fees="0.00", total="10.00")
        )
    )
    _, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert reports[0]["difference_eur"] == "0.00"
    assert reports[0]["warnings"] == []


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (order(status="pending"), "completed"),
        (order(currency="USD"), "EUR"),
        (order(quantity=1.09), "decimal string"),
        (order(quantity="0"), "positive"),
        (order(unit_price="1.1234567"), "at most 6"),
        (order(fees="-0.01"), "decimal string"),
        (order(side="dividend"), "side must"),
        (order(date_local="not-a-date"), "ISO local timestamp"),
        (
            order(
                date_local=(date.today() + timedelta(days=1)).isoformat()
                + "T10:00:00"
            ),
            "future",
        ),
        ({"entry_id": "missing-fields"}, "isin is required"),
        (None, "JSON object"),
    ],
)
def test_invalid_order_is_reported_without_blocking_valid_rows(
    source, message
):
    parsed = parse_bunq_export(export(order(entry_id="valid"), source))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert len(transactions) == 1
    assert reports[0]["status"] == "ready"
    assert reports[1]["status"] == "rejected"
    assert message in reports[1]["reason"]


def test_missing_mapping_excludes_only_its_instrument_rows():
    second = order(
        entry_id="other",
        isin="IE00BGV5VN51",
        asset="AI & Big Data",
    )
    parsed = parse_bunq_export(export(order(), second))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert len(transactions) == 1
    assert [report["status"] for report in reports] == [
        "ready",
        "needs_mapping",
    ]


def test_distinct_entry_ids_are_not_collapsed():
    parsed = parse_bunq_export(
        export(order(entry_id="one"), order(entry_id="two"))
    )
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert len(transactions) == 2
    assert [report["entry_id"] for report in reports] == ["one", "two"]


def test_unknown_or_malformed_export_envelope_fails():
    with pytest.raises(
        BunqImportError, match="unsupported Bunq schema_version"
    ):
        parse_bunq_export({"schema_version": "2.0", "orders": []})
    with pytest.raises(BunqImportError, match="orders array"):
        parse_bunq_export({"schema_version": "1.0", "orders": {}})
    with pytest.raises(BunqImportError, match="JSON object"):
        parse_bunq_export([])


def test_source_metadata_stays_in_report_not_transaction_json():
    parsed = parse_bunq_export(export(order()))
    transactions, reports = parsed.transactions({"IE00B0M62Y33": mapping()})

    assert set(transactions[0]) == {
        "side",
        "instrument_type",
        "ticker",
        "exchange",
        "trade_date",
        "quantity",
        "unit_price_eur",
        "gross_amount_eur",
        "fee_eur",
        "currency",
        "name",
    }
    assert reports[0]["source"]["source_url"] == order()["source_url"]
    assert reports[0]["isin"] == order()["isin"]
    assert reports[0]["source"]["name"] == "AEX Short Name"
    assert reports[0]["source"]["legal_name"] == "iShares AEX UCITS ETF"
    assert isinstance(Decimal(transactions[0]["gross_amount_eur"]), Decimal)
