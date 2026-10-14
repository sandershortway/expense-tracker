from __future__ import annotations

from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from investment_ledger.holdings import HoldingsReport, compute_holdings
from investment_ledger.storage import Ledger
from investment_ledger.valuation import (
    Price,
    load_prices,
    portfolio_return,
    value_position,
)

_HEADERS = (
    "Ticker",
    "Exchange",
    "Type",
    "Name",
    "Quantity",
    "Avg cost (EUR)",
    "Cost basis (EUR)",
    "Price (EUR)",
    "Market value (EUR)",
    "Unrealized P&L (EUR)",
    "Total return",
    "Realized P&L (EUR)",
    "Fees (EUR)",
)

_STYLE = """
body { font-family: sans-serif; margin: 2rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.7rem; }
th { background: #f2f2f2; text-align: left; }
td.num { text-align: right; }
td.pos { color: #137333; }
td.neg { color: #b3261e; }
tfoot td { font-weight: bold; }
p.note { color: #555; font-size: 0.9rem; }
"""


def _text(value: object) -> str:
    return f"<td>{escape('' if value is None else str(value))}</td>"


def _num(value: object, *, signed: bool = False, suffix: str = "") -> str:
    if value is None:
        return '<td class="num"></td>'
    css = "num"
    if signed and isinstance(value, Decimal) and value != 0:
        css += " pos" if value > 0 else " neg"
    shown = f"{value:+}" if signed and isinstance(value, Decimal) else value
    return f'<td class="{css}">{escape(str(shown))}{suffix}</td>'


def render_positions(
    report: HoldingsReport, prices: dict[str, Price] | None = None
) -> str:
    prices = prices or {}
    positions = report.positions
    valuations = [value_position(p, prices) for p in positions]
    rows = []
    for position, valuation in zip(positions, valuations, strict=True):
        data = position.to_mapping()
        rows.append(
            "<tr>"
            + _text(data["ticker"])
            + _text(data["exchange"])
            + _text(data["instrument_type"])
            + _text(data["name"])
            + _num(data["net_quantity"])
            + _num(data["average_cost_eur"])
            + _num(data["cost_basis_eur"])
            + _num(valuation.price and valuation.price.price_eur)
            + _num(valuation.market_value_eur)
            + _num(valuation.unrealized_pnl_eur, signed=True)
            + _num(valuation.total_return_pct, signed=True, suffix="%")
            + _num(data["realized_pnl_eur"])
            + _num(data["total_fees_eur"])
            + "</tr>"
        )
    if not rows:
        rows.append(
            f'<tr><td colspan="{len(_HEADERS)}">No positions</td></tr>'
        )

    totals = report.to_mapping()["totals"]
    market_value, total_return = portfolio_return(positions, valuations)
    unrealized = (
        None
        if market_value is None
        else market_value - report.totals()["cost_basis_eur"]
    )
    footer = (
        '<tr><td colspan="6">Total</td>'
        + _num(totals["cost_basis_eur"])
        + "<td></td>"
        + _num(market_value)
        + _num(unrealized, signed=True)
        + _num(total_return, signed=True, suffix="%")
        + _num(totals["realized_pnl_eur"])
        + _num(totals["total_fees_eur"])
        + "</tr>"
    )
    dates = sorted({p.as_of for p in prices.values() if p.as_of})
    note = (
        f"Prices as of {escape(', '.join(dates))}. "
        if dates
        else "No price file found. "
    ) + (
        "Total return = (market value + sale proceeds - amount invested "
        "incl. fees) / amount invested."
    )
    header = "".join(f"<th>{escape(label)}</th>" for label in _HEADERS)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Positions</title><style>{_STYLE}</style></head><body>"
        f"<h1>Positions</h1><table><thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody><tfoot>{footer}</tfoot>"
        f'</table><p class="note">{note}</p></body></html>'
    )


def make_server(
    database: str, host: str, port: int, prices_path: Path | None = None
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            with Ledger(database) as ledger:
                report = compute_holdings(ledger.list_transactions())
            prices = load_prices(prices_path) if prices_path else {}
            body = render_positions(report, prices).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer((host, port), Handler)
