from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any


class ValidationError(ValueError):
    pass


_DECIMAL_PATTERN = re.compile(r"\d+(?:\.\d+)?\Z")
_ALLOWED_FIELDS = {
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
_CENT = Decimal("0.01")


def _decimal(
    value: Any, field: str, places: int, *, allow_zero: bool = False
) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValidationError(f"{field} must be supplied as a decimal string")
    raw = str(value).strip()
    if not _DECIMAL_PATTERN.fullmatch(raw):
        raise ValidationError(f"{field} must be a non-negative decimal number")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValidationError(
            f"{field} is not a valid decimal number"
        ) from exc
    if not number.is_finite():
        raise ValidationError(f"{field} must be finite")
    if number.as_tuple().exponent < -places:
        raise ValidationError(
            f"{field} may have at most {places} decimal places"
        )
    if number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValidationError(f"{field} must be {qualifier}")
    return number


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} is required")
    return value.strip()


@dataclass(frozen=True)
class TransactionData:
    side: str
    instrument_type: str
    ticker: str
    exchange: str
    trade_date: date
    quantity: Decimal
    unit_price_eur: Decimal
    gross_amount_eur: Decimal
    fee_eur: Decimal | None = None
    currency: str = "EUR"
    name: str | None = None

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> TransactionData:
        if not isinstance(values, dict):
            raise ValidationError("transaction must be a JSON object")
        unknown = set(values) - _ALLOWED_FIELDS
        if unknown:
            raise ValidationError(
                f"unknown field(s): {', '.join(sorted(unknown))}"
            )

        side = _required_text(values.get("side"), "side").lower()
        if side not in {"buy", "sell"}:
            raise ValidationError("side must be 'buy' or 'sell'")

        instrument_type = _required_text(
            values.get("instrument_type"), "instrument_type"
        ).lower()
        if instrument_type not in {"stock", "etf"}:
            raise ValidationError("instrument_type must be 'stock' or 'etf'")

        ticker = _required_text(values.get("ticker"), "ticker").upper()
        exchange = _required_text(values.get("exchange"), "exchange").upper()
        date_value = _required_text(values.get("trade_date"), "trade_date")
        try:
            trade_date = date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValidationError(
                "trade_date must be a valid YYYY-MM-DD date"
            ) from exc
        if trade_date.isoformat() != date_value:
            raise ValidationError("trade_date must use YYYY-MM-DD format")
        if trade_date > date.today():
            raise ValidationError("trade_date cannot be in the future")

        quantity = _decimal(values.get("quantity"), "quantity", 8)
        unit_price = _decimal(
            values.get("unit_price_eur"), "unit_price_eur", 6
        )
        gross_amount = _decimal(
            values.get("gross_amount_eur"), "gross_amount_eur", 2
        )
        with localcontext() as context:
            context.prec = max(
                28,
                len(quantity.as_tuple().digits)
                + len(unit_price.as_tuple().digits)
                + 4,
            )
            expected_gross = (quantity * unit_price).quantize(
                _CENT, rounding=ROUND_HALF_UP
            )
        if gross_amount != expected_gross:
            raise ValidationError(
                "gross_amount_eur must equal quantity * unit_price_eur "
                f"rounded half-up to cents ({expected_gross:.2f})"
            )

        fee_value = values.get("fee_eur")
        fee = (
            None
            if fee_value is None
            else _decimal(fee_value, "fee_eur", 2, allow_zero=True)
        )
        currency = _required_text(
            values.get("currency", "EUR"), "currency"
        ).upper()
        if currency != "EUR":
            raise ValidationError("currency must be EUR")

        name_value = values.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise ValidationError("name must be a string")
        name = name_value.strip() or None if name_value is not None else None

        return cls(
            side=side,
            instrument_type=instrument_type,
            ticker=ticker,
            exchange=exchange,
            trade_date=trade_date,
            quantity=quantity,
            unit_price_eur=unit_price,
            gross_amount_eur=gross_amount,
            fee_eur=fee,
            currency=currency,
            name=name,
        )

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "side": self.side,
            "instrument_type": self.instrument_type,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "trade_date": self.trade_date.isoformat(),
            "quantity": str(self.quantity),
            "unit_price_eur": str(self.unit_price_eur),
            "gross_amount_eur": str(self.gross_amount_eur),
            "fee_eur": None if self.fee_eur is None else str(self.fee_eur),
            "currency": self.currency,
            "name": self.name,
        }

    def duplicate_key(self) -> tuple[object, ...]:
        return (
            self.ticker,
            self.exchange,
            self.side,
            self.trade_date,
            self.quantity,
            self.unit_price_eur,
            self.gross_amount_eur,
            self.fee_eur,
        )


@dataclass(frozen=True)
class StoredTransaction:
    transaction_id: str
    entry_order: int
    data: TransactionData
    created_at: str
    updated_at: str

    def to_mapping(self) -> dict[str, str | int | None]:
        return {
            "transaction_id": self.transaction_id,
            "entry_order": self.entry_order,
            **self.data.to_mapping(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def utc_timestamp() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
