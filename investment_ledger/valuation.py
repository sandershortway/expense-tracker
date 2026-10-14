from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from investment_ledger.holdings import Position

_CENT = Decimal("0.01")


class PriceFileError(ValueError):
    pass


@dataclass(frozen=True)
class Price:
    price_eur: Decimal
    as_of: str | None
    source: str | None


@dataclass(frozen=True)
class Valuation:
    price: Price | None
    market_value_eur: Decimal | None
    unrealized_pnl_eur: Decimal | None
    total_return_pct: Decimal | None


def position_key(ticker: str, exchange: str) -> str:
    return f"{ticker.upper()}@{exchange.upper()}"


def load_prices(path: Path) -> dict[str, Price]:
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriceFileError(f"could not read price file: {exc}") from exc
    entries = document.get("prices") if isinstance(document, dict) else None
    if not isinstance(entries, dict):
        raise PriceFileError("price file must contain a 'prices' object")
    prices: dict[str, Price] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict) or not isinstance(
            entry.get("price_eur"), str
        ):
            raise PriceFileError(f"{key}: price_eur must be a decimal string")
        try:
            value = Decimal(entry["price_eur"])
        except InvalidOperation as exc:
            raise PriceFileError(f"{key}: invalid price_eur") from exc
        if not value.is_finite() or value <= 0:
            raise PriceFileError(f"{key}: price_eur must be positive")
        ticker, _, exchange = key.partition("@")
        prices[position_key(ticker, exchange)] = Price(
            value, entry.get("as_of"), entry.get("source")
        )
    return prices


def _return_pct(gain: Decimal, invested: Decimal) -> Decimal | None:
    if invested <= 0:
        return None
    return (gain / invested * 100).quantize(_CENT, rounding=ROUND_HALF_UP)


def value_position(position: Position, prices: dict[str, Price]) -> Valuation:
    price = prices.get(position_key(position.ticker, position.exchange))
    if price is None:
        return Valuation(None, None, None, None)
    market_value = (position.net_quantity * price.price_eur).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
    gain = (
        market_value
        + position.total_proceeds_eur
        - position.total_invested_eur
    )
    return Valuation(
        price,
        market_value,
        market_value - position.cost_basis_eur,
        _return_pct(gain, position.total_invested_eur),
    )


def portfolio_return(
    positions: list[Position], valuations: list[Valuation]
) -> tuple[Decimal | None, Decimal | None]:
    if not positions or any(
        v.market_value_eur is None
        for p, v in zip(positions, valuations, strict=True)
        if p.net_quantity != 0
    ):
        return None, None
    market_value = sum(
        (v.market_value_eur or Decimal(0) for v in valuations), Decimal(0)
    )
    invested = sum((p.total_invested_eur for p in positions), Decimal(0))
    proceeds = sum((p.total_proceeds_eur for p in positions), Decimal(0))
    return market_value, _return_pct(
        market_value + proceeds - invested, invested
    )
