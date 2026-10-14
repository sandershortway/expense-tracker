from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any

from investment_ledger.domain import TransactionData, ValidationError

_SUPPORTED_VERSION = "1.0"
_DECIMAL_PATTERN = re.compile(r"\d+(?:\.\d+)?\Z")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


class BunqImportError(ValueError):
    pass


@dataclass(frozen=True)
class InstrumentMapping:
    instrument_type: str
    ticker: str
    exchange: str

    @classmethod
    def from_values(
        cls, instrument_type: str, ticker: str, exchange: str
    ) -> InstrumentMapping:
        values = {
            "side": "buy",
            "instrument_type": instrument_type,
            "ticker": ticker,
            "exchange": exchange,
            "trade_date": "2000-01-01",
            "quantity": "1",
            "unit_price_eur": "1.00",
            "gross_amount_eur": "1.00",
        }
        transaction = TransactionData.from_mapping(values)
        return cls(
            transaction.instrument_type,
            transaction.ticker,
            transaction.exchange,
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "instrument_type": self.instrument_type,
            "ticker": self.ticker,
            "exchange": self.exchange,
        }


@dataclass(frozen=True)
class BunqOrderCandidate:
    index: int
    source: dict[str, Any]
    transaction_fields: dict[str, str | None]
    calculated_total_eur: Decimal
    total_difference_eur: Decimal | None
    warnings: tuple[str, ...]

    @property
    def entry_id(self) -> str:
        return str(self.source["entry_id"])

    @property
    def isin(self) -> str:
        return _text(self.source["isin"], "isin")

    def transaction(self, mapping: InstrumentMapping) -> dict[str, str | None]:
        row = {
            **self.transaction_fields,
            **mapping.to_mapping(),
        }
        validated = TransactionData.from_mapping(row)
        return validated.to_mapping()

    def report_mapping(
        self,
        mapping: InstrumentMapping | None = None,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        transaction = None
        status = (
            "needs_mapping" if mapping is None and reason is None else "ready"
        )
        if reason is not None:
            status = "needs_review"
        elif mapping is not None:
            try:
                transaction = self.transaction(mapping)
            except ValidationError as exc:
                reason = str(exc)
                status = "needs_review"

        result = {
            "index": self.index,
            "entry_id": self.entry_id,
            "status": status,
            "isin": self.isin,
            "source": {
                key: self.source.get(key)
                for key in (
                    "order_id",
                    "asset",
                    "name",
                    "legal_name",
                    "side",
                    "status",
                    "date_local",
                    "timezone",
                    "quantity",
                    "unit_price",
                    "currency",
                    "fees",
                    "total",
                    "source_url",
                )
            },
            "converted": transaction or dict(self.transaction_fields),
            "calculated_total_eur": str(self.calculated_total_eur),
            "difference_eur": (
                None
                if self.total_difference_eur is None
                else str(self.total_difference_eur)
            ),
            "warnings": list(self.warnings),
        }
        if mapping is not None:
            result["mapping"] = mapping.to_mapping()
        if reason is not None:
            result["reason"] = reason
        return result


@dataclass(frozen=True)
class RejectedOrder:
    index: int
    source: Any
    reason: str

    def report_mapping(self) -> dict[str, Any]:
        entry_id = (
            self.source.get("entry_id")
            if isinstance(self.source, dict)
            else None
        )
        return {
            "index": self.index,
            "entry_id": entry_id,
            "status": "rejected",
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class ParsedBunqExport:
    schema_version: str
    export_date: str | None
    coverage: dict[str, Any] | None
    candidates: tuple[BunqOrderCandidate, ...]
    rejected: tuple[RejectedOrder, ...]
    order_count: int

    @property
    def isins(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(candidate.isin for candidate in self.candidates)
        )

    def transactions(
        self,
        mappings: dict[str, InstrumentMapping],
        mapping_errors: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, str | None]], list[dict[str, Any]]]:
        mapping_errors = mapping_errors or {}
        transactions: list[dict[str, str | None]] = []
        reports: dict[int, dict[str, Any]] = {
            rejected.index: rejected.report_mapping()
            for rejected in self.rejected
        }
        for candidate in self.candidates:
            mapping = mappings.get(candidate.isin)
            if mapping is None:
                reports[candidate.index] = candidate.report_mapping(
                    reason=mapping_errors.get(candidate.isin)
                )
                continue
            report = candidate.report_mapping(mapping)
            reports[candidate.index] = report
            if report["status"] == "ready":
                transactions.append(report["converted"])
        ordered_reports = [
            reports[index] for index in range(1, self.order_count + 1)
        ]
        return transactions, ordered_reports


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required and must be a non-empty string")
    return value.strip()


def _decimal(
    value: Any, field: str, places: int, *, allow_zero: bool = False
) -> Decimal:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is invalid") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    if number.as_tuple().exponent < -places:
        raise ValueError(f"{field} may have at most {places} decimal places")
    if number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field} must be {qualifier}")
    return number


def _parse_order(index: int, source: Any) -> BunqOrderCandidate:
    if not isinstance(source, dict):
        raise ValueError("order must be a JSON object")
    _text(source.get("entry_id"), "entry_id")
    _text(source.get("isin"), "isin")
    asset = _text(source.get("asset"), "asset")
    name_value = source.get("name")
    name = asset if name_value is None else _text(name_value, "name")
    side = _text(source.get("side"), "side").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    if _text(source.get("status"), "status").lower() != "completed":
        raise ValueError("only completed orders can be imported")
    currency = _text(source.get("currency"), "currency").upper()
    if currency != "EUR":
        raise ValueError("only EUR orders can be imported")
    timezone = source.get("timezone")
    if timezone is not None and not isinstance(timezone, str):
        raise ValueError("timezone must be a string or null")

    date_local = _text(source.get("date_local"), "date_local")
    if "T" not in date_local:
        raise ValueError("date_local must be an ISO local timestamp")
    try:
        local_datetime = datetime.fromisoformat(date_local)
    except ValueError as exc:
        raise ValueError("date_local must be an ISO local timestamp") from exc
    trade_date = local_datetime.date().isoformat()
    if local_datetime.date() > date.today():
        raise ValueError("trade date cannot be in the future")

    quantity = _decimal(source.get("quantity"), "quantity", 8)
    unit_price = _decimal(source.get("unit_price"), "unit_price", 6)
    fee_value = source.get("fees")
    fee = (
        None
        if fee_value is None
        else _decimal(fee_value, "fees", 2, allow_zero=True)
    )
    total_value = source.get("total")
    total = (
        None
        if total_value is None
        else _decimal(total_value, "total", 2, allow_zero=True)
    )

    with localcontext() as context:
        context.prec = max(
            28,
            len(quantity.as_tuple().digits)
            + len(unit_price.as_tuple().digits)
            + 4,
        )
        gross = (quantity * unit_price).quantize(_CENT, rounding=ROUND_HALF_UP)
    calculated_total = gross + (fee or _ZERO)
    difference = None if total is None else calculated_total - total
    warnings = ()
    if difference is not None and difference != 0:
        warnings = (
            "calculated gross plus fee differs from Bunq total "
            f"by EUR {difference:.2f}",
        )

    fields: dict[str, str | None] = {
        "side": side,
        "trade_date": trade_date,
        "quantity": str(quantity),
        "unit_price_eur": str(unit_price),
        "gross_amount_eur": str(gross),
        "fee_eur": None if fee is None else str(fee),
        "currency": currency,
        "name": name,
    }
    return BunqOrderCandidate(
        index=index,
        source=source,
        transaction_fields=fields,
        calculated_total_eur=calculated_total,
        total_difference_eur=difference,
        warnings=warnings,
    )


def parse_bunq_export(document: Any) -> ParsedBunqExport:
    if not isinstance(document, dict):
        raise BunqImportError("Bunq export must be a JSON object")
    version = document.get("schema_version")
    if version != _SUPPORTED_VERSION:
        raise BunqImportError(
            f"unsupported Bunq schema_version {version!r}; "
            f"expected {_SUPPORTED_VERSION!r}"
        )
    orders = document.get("orders")
    if not isinstance(orders, list):
        raise BunqImportError("Bunq export must contain an orders array")

    candidates: list[BunqOrderCandidate] = []
    rejected: list[RejectedOrder] = []
    for index, source in enumerate(orders, start=1):
        try:
            candidates.append(_parse_order(index, source))
        except (ValueError, ValidationError) as exc:
            rejected.append(RejectedOrder(index, source, str(exc)))

    coverage = document.get("coverage")
    return ParsedBunqExport(
        schema_version=version,
        export_date=(
            document.get("export_date")
            if isinstance(document.get("export_date"), str)
            else None
        ),
        coverage=coverage if isinstance(coverage, dict) else None,
        candidates=tuple(candidates),
        rejected=tuple(rejected),
        order_count=len(orders),
    )
