from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from investment_ledger.domain import (
    StoredTransaction,
    TransactionData,
    utc_timestamp,
)

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE transactions (
    entry_order INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL UNIQUE,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    instrument_type TEXT NOT NULL CHECK (instrument_type IN ('stock', 'etf')),
    ticker TEXT NOT NULL CHECK (length(ticker) > 0 AND ticker = upper(ticker)),
    exchange TEXT NOT NULL CHECK (
        length(exchange) > 0 AND exchange = upper(exchange)
    ),
    name TEXT,
    trade_date TEXT NOT NULL,
    quantity TEXT NOT NULL CHECK (length(quantity) > 0),
    unit_price_eur TEXT NOT NULL CHECK (length(unit_price_eur) > 0),
    gross_amount_eur TEXT NOT NULL CHECK (length(gross_amount_eur) > 0),
    fee_eur TEXT CHECK (fee_eur IS NULL OR length(fee_eur) > 0),
    currency TEXT NOT NULL CHECK (currency = 'EUR'),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class LedgerError(Exception):
    pass


class TransactionNotFound(LedgerError):
    pass


class Ledger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(
        self, exc_type: object, exc_value: object, traceback: object
    ) -> None:
        self.close()

    def _initialize(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise LedgerError(
                f"database schema version {version} is newer than supported "
                f"version {SCHEMA_VERSION}"
            )
        if version == SCHEMA_VERSION:
            return
        existing_tables = self.connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if existing_tables:
            raise LedgerError("database has an unsupported unversioned schema")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(SCHEMA)
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.connection.commit()
        except sqlite3.Error:
            self.connection.rollback()
            raise

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredTransaction:
        data = TransactionData.from_mapping(
            {
                "side": row["side"],
                "instrument_type": row["instrument_type"],
                "ticker": row["ticker"],
                "exchange": row["exchange"],
                "name": row["name"],
                "trade_date": row["trade_date"],
                "quantity": row["quantity"],
                "unit_price_eur": row["unit_price_eur"],
                "gross_amount_eur": row["gross_amount_eur"],
                "fee_eur": row["fee_eur"],
                "currency": row["currency"],
            }
        )
        return StoredTransaction(
            transaction_id=row["transaction_id"],
            entry_order=row["entry_order"],
            data=data,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _insert(self, data: TransactionData) -> StoredTransaction:
        timestamp = utc_timestamp()
        transaction_id = uuid4().hex
        cursor = self.connection.execute(
            """INSERT INTO transactions (
                transaction_id, side, instrument_type, ticker, exchange, name,
                trade_date, quantity, unit_price_eur,
                gross_amount_eur, fee_eur,
                currency, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transaction_id,
                data.side,
                data.instrument_type,
                data.ticker,
                data.exchange,
                data.name,
                data.trade_date.isoformat(),
                str(data.quantity),
                str(data.unit_price_eur),
                str(data.gross_amount_eur),
                None if data.fee_eur is None else str(data.fee_eur),
                data.currency,
                timestamp,
                timestamp,
            ),
        )
        row = self.connection.execute(
            "SELECT * FROM transactions WHERE entry_order = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return self._from_row(row)

    def add(self, data: TransactionData) -> StoredTransaction:
        return self.add_many([data])[0]

    def add_many(
        self, transactions: list[TransactionData]
    ) -> list[StoredTransaction]:
        with self.connection:
            return [self._insert(data) for data in transactions]

    def list_transactions(self) -> list[StoredTransaction]:
        rows = self.connection.execute(
            "SELECT * FROM transactions ORDER BY trade_date, entry_order"
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, transaction_id: str) -> StoredTransaction:
        row = self.connection.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if row is None:
            raise TransactionNotFound(
                f"transaction {transaction_id!r} was not found"
            )
        return self._from_row(row)

    def update(
        self, transaction_id: str, changes: dict[str, object]
    ) -> StoredTransaction:
        current = self.get(transaction_id)
        values = current.data.to_mapping()
        values.update(changes)
        updated = TransactionData.from_mapping(values)
        timestamp = utc_timestamp()
        with self.connection:
            cursor = self.connection.execute(
                """UPDATE transactions SET
                    side = ?, instrument_type = ?, ticker = ?, exchange = ?,
                    name = ?, trade_date = ?, quantity = ?, unit_price_eur = ?,
                    gross_amount_eur = ?, fee_eur = ?, currency = ?,
                    updated_at = ?
                    WHERE transaction_id = ?""",
                (
                    updated.side,
                    updated.instrument_type,
                    updated.ticker,
                    updated.exchange,
                    updated.name,
                    updated.trade_date.isoformat(),
                    str(updated.quantity),
                    str(updated.unit_price_eur),
                    str(updated.gross_amount_eur),
                    None if updated.fee_eur is None else str(updated.fee_eur),
                    updated.currency,
                    timestamp,
                    transaction_id,
                ),
            )
            if cursor.rowcount == 0:
                raise TransactionNotFound(
                    f"transaction {transaction_id!r} was not found"
                )
        return self.get(transaction_id)

    def delete(self, transaction_id: str) -> None:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM transactions WHERE transaction_id = ?",
                (transaction_id,),
            )
            if cursor.rowcount == 0:
                raise TransactionNotFound(
                    f"transaction {transaction_id!r} was not found"
                )

    def has_duplicate(self, data: TransactionData) -> bool:
        rows = self.connection.execute(
            """SELECT * FROM transactions
               WHERE ticker = ? AND exchange = ? AND side = ?
                 AND trade_date = ?""",
            (
                data.ticker,
                data.exchange,
                data.side,
                data.trade_date.isoformat(),
            ),
        ).fetchall()
        return any(
            self._from_row(row).data.duplicate_key() == data.duplicate_key()
            for row in rows
        )
