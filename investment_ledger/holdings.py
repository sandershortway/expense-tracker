from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from investment_ledger.domain import StoredTransaction

_CENT = Decimal("0.01")
_UNIT_PRICE_QUANTUM = Decimal("0.000001")

_ZERO = Decimal("0")


def _cents(value: Decimal) -> str:
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


@dataclass
class Position:
    ticker: str
    exchange: str
    instrument_type: str
    name: str | None
    net_quantity: Decimal
    cost_basis_eur: Decimal
    total_invested_eur: Decimal
    total_proceeds_eur: Decimal
    realized_pnl_eur: Decimal
    total_fees_eur: Decimal
    transaction_count: int
    first_trade_date: date
    last_trade_date: date
    warnings: list[str] = field(default_factory=list)

    @property
    def average_cost_eur(self) -> Decimal | None:
        if self.net_quantity <= 0:
            return None
        with localcontext() as context:
            context.prec = 40
            average = self.cost_basis_eur / self.net_quantity
        return average.quantize(_UNIT_PRICE_QUANTUM, rounding=ROUND_HALF_UP)

    def to_mapping(self) -> dict[str, Any]:
        average = self.average_cost_eur
        return {
            "ticker": self.ticker,
            "exchange": self.exchange,
            "instrument_type": self.instrument_type,
            "name": self.name,
            "net_quantity": str(self.net_quantity),
            "cost_basis_eur": _cents(self.cost_basis_eur),
            "average_cost_eur": None if average is None else str(average),
            "total_invested_eur": _cents(self.total_invested_eur),
            "total_proceeds_eur": _cents(self.total_proceeds_eur),
            "realized_pnl_eur": _cents(self.realized_pnl_eur),
            "total_fees_eur": _cents(self.total_fees_eur),
            "transaction_count": self.transaction_count,
            "first_trade_date": self.first_trade_date.isoformat(),
            "last_trade_date": self.last_trade_date.isoformat(),
            "warnings": list(self.warnings),
        }


@dataclass
class HoldingsReport:
    positions: list[Position]

    def totals(self) -> dict[str, Decimal]:
        return {
            "cost_basis_eur": sum(
                (p.cost_basis_eur for p in self.positions), _ZERO
            ),
            "total_invested_eur": sum(
                (p.total_invested_eur for p in self.positions), _ZERO
            ),
            "total_proceeds_eur": sum(
                (p.total_proceeds_eur for p in self.positions), _ZERO
            ),
            "realized_pnl_eur": sum(
                (p.realized_pnl_eur for p in self.positions), _ZERO
            ),
            "total_fees_eur": sum(
                (p.total_fees_eur for p in self.positions), _ZERO
            ),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            "count": len(self.positions),
            "holdings": [position.to_mapping() for position in self.positions],
            "totals": {
                key: _cents(value) for key, value in self.totals().items()
            },
        }


def compute_holdings(
    transactions: Iterable[StoredTransaction],
) -> HoldingsReport:
    grouped: dict[tuple[str, str], list[StoredTransaction]] = {}
    for transaction in transactions:
        key = (transaction.data.ticker, transaction.data.exchange)
        grouped.setdefault(key, []).append(transaction)
    positions = [
        _build_position(identity, group) for identity, group in grouped.items()
    ]
    positions.sort(key=lambda p: (p.ticker, p.exchange))
    return HoldingsReport(positions)


def _build_position(
    identity: tuple[str, str],
    transactions: list[StoredTransaction],
) -> Position:
    ticker, exchange = identity
    ordered = sorted(
        transactions, key=lambda t: (t.data.trade_date, t.entry_order)
    )
    quantity = _ZERO
    cost_basis = _ZERO
    invested = _ZERO
    proceeds = _ZERO
    realized = _ZERO
    fees = _ZERO
    instrument_type = ordered[0].data.instrument_type
    name: str | None = None
    warnings: list[str] = []

    for transaction in ordered:
        data = transaction.data
        instrument_type = data.instrument_type
        if data.name is not None:
            name = data.name
        fee = data.fee_eur or _ZERO
        fees += fee
        if data.side == "buy":
            quantity += data.quantity
            invested += data.gross_amount_eur + fee
            cost_basis += data.gross_amount_eur + fee
            continue

        proceeds += data.gross_amount_eur - fee
        if quantity <= 0 or data.quantity > quantity:
            excess = data.quantity - max(quantity, _ZERO)
            warnings.append(
                f"sold {excess} more than held on {data.trade_date}"
            )
            released = cost_basis
        else:
            with localcontext() as context:
                context.prec = 40
                released = cost_basis * data.quantity / quantity
        realized += data.gross_amount_eur - fee - released
        cost_basis -= released
        quantity -= data.quantity

    return Position(
        ticker=ticker,
        exchange=exchange,
        instrument_type=instrument_type,
        name=name,
        net_quantity=quantity,
        cost_basis_eur=cost_basis,
        total_invested_eur=invested,
        total_proceeds_eur=proceeds,
        realized_pnl_eur=realized,
        total_fees_eur=fees,
        transaction_count=len(ordered),
        first_trade_date=ordered[0].data.trade_date,
        last_trade_date=ordered[-1].data.trade_date,
        warnings=warnings,
    )
