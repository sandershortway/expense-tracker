import sqlite3

import pytest

from investment_ledger.domain import TransactionData
from investment_ledger.storage import (
    SCHEMA_VERSION,
    Ledger,
    LedgerError,
    TransactionNotFound,
)


def transaction(**overrides):
    values = {
        "side": "buy",
        "instrument_type": "etf",
        "ticker": "VT",
        "exchange": "XNYS",
        "trade_date": "2024-02-03",
        "quantity": "3.25000001",
        "unit_price_eur": "10.120001",
        "gross_amount_eur": "32.89",
        "fee_eur": None,
    }
    values.update(overrides)
    return TransactionData.from_mapping(values)


def test_initializes_versioned_schema_and_persists_exact_values(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    with Ledger(path) as ledger:
        created = ledger.add(transaction())
        assert created.entry_order == 1
        assert (
            ledger.connection.execute("PRAGMA user_version").fetchone()[0]
            == SCHEMA_VERSION
        )

    with Ledger(path) as ledger:
        stored = ledger.get(created.transaction_id)
        assert stored.data.quantity == transaction().quantity
        assert stored.data.unit_price_eur == transaction().unit_price_eur
        assert stored.data.to_mapping()["quantity"] == "3.25000001"
        assert stored.data.fee_eur is None


def test_orders_by_trade_date_then_entry_order(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        first = ledger.add(transaction(trade_date="2024-02-03"))
        second = ledger.add(transaction(trade_date="2024-02-03", ticker="SPY"))
        older = ledger.add(transaction(trade_date="2024-01-01", ticker="QQQ"))

        listed = ledger.list_transactions()

    assert [item.transaction_id for item in listed] == [
        older.transaction_id,
        first.transaction_id,
        second.transaction_id,
    ]


def test_update_persists_and_refreshes_metadata(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    with Ledger(path) as ledger:
        created = ledger.add(transaction())
        updated = ledger.update(created.transaction_id, {"name": "Fund"})
        assert updated.data.name == "Fund"
        assert updated.created_at == created.created_at
        assert updated.updated_at >= created.updated_at

    with Ledger(path) as ledger:
        assert ledger.get(created.transaction_id).data.name == "Fund"


def test_update_validates_full_result_and_rolls_back_invalid_values(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        created = ledger.add(transaction())
        with pytest.raises(ValueError, match="gross_amount_eur"):
            ledger.update(created.transaction_id, {"quantity": "4"})

        assert (
            ledger.get(created.transaction_id).data.quantity
            == transaction().quantity
        )


def test_delete_persists_and_unknown_ids_raise(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        created = ledger.add(transaction())
        ledger.delete(created.transaction_id)
        assert ledger.list_transactions() == []
        with pytest.raises(TransactionNotFound):
            ledger.delete(created.transaction_id)

    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        assert ledger.list_transactions() == []


def test_duplicate_detection_ignores_name_but_distinguishes_fee(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        original = transaction(name="Original")
        ledger.add(original)
        assert ledger.has_duplicate(transaction(name="Different"))
        assert not ledger.has_duplicate(transaction(fee_eur="0.00"))


def test_batch_write_rolls_back_when_writer_fails(tmp_path, monkeypatch):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        original_insert = ledger._insert
        insert_count = 0

        def fail_on_second(data):
            nonlocal insert_count
            insert_count += 1
            if insert_count == 2:
                raise sqlite3.IntegrityError("forced failure")
            return original_insert(data)

        monkeypatch.setattr(ledger, "_insert", fail_on_second)
        with pytest.raises(sqlite3.IntegrityError):
            ledger.add_many([transaction(), transaction(ticker="SPY")])
        assert ledger.list_transactions() == []


def test_refuses_newer_or_unknown_unversioned_schemas(tmp_path):
    newer_path = tmp_path / "newer.sqlite3"
    connection = sqlite3.connect(newer_path)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    connection.close()
    with pytest.raises(LedgerError, match="newer"):
        Ledger(newer_path)

    legacy_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(legacy_path)
    connection.execute("CREATE TABLE unknown_table (id INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(LedgerError, match="unversioned"):
        Ledger(legacy_path)


def test_schema_rejects_invalid_side(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as ledger:
        with pytest.raises(sqlite3.IntegrityError):
            with ledger.connection:
                ledger.connection.execute(
                    """INSERT INTO transactions (
                        transaction_id, side, instrument_type, ticker,
                        exchange,
                        trade_date, quantity, unit_price_eur, gross_amount_eur,
                        currency, created_at, updated_at
                    ) VALUES ('id', 'hold', 'stock', 'ACME', 'XNAS',
                        '2024-01-01', '1', '1', '1', 'EUR', 'now', 'now')"""
                )
