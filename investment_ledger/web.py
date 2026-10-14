from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from investment_ledger.holdings import HoldingsReport, compute_holdings
from investment_ledger.storage import Ledger

_COLUMNS = (
    ("Ticker", "ticker"),
    ("Exchange", "exchange"),
    ("Type", "instrument_type"),
    ("Name", "name"),
    ("Quantity", "net_quantity"),
    ("Cost basis (EUR)", "cost_basis_eur"),
    ("Avg cost (EUR)", "average_cost_eur"),
    ("Realized P&L (EUR)", "realized_pnl_eur"),
    ("Fees (EUR)", "total_fees_eur"),
)

_STYLE = """
body { font-family: sans-serif; margin: 2rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.7rem; }
th { background: #f2f2f2; text-align: left; }
td.num { text-align: right; }
tfoot td { font-weight: bold; }
"""


def render_positions(report: HoldingsReport) -> str:
    data = report.to_mapping()
    header = "".join(f"<th>{escape(label)}</th>" for label, _ in _COLUMNS)
    rows = []
    for position in data["holdings"]:
        cells = []
        for _, key in _COLUMNS:
            value = position[key]
            css = ' class="num"' if key.endswith(("_eur", "quantity")) else ""
            cells.append(f"<td{css}>{escape(str(value or ''))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    if not rows:
        rows.append(
            f'<tr><td colspan="{len(_COLUMNS)}">No positions</td></tr>'
        )
    totals = data["totals"]
    footer = (
        '<tr><td colspan="5">Total</td>'
        f'<td class="num">{totals["cost_basis_eur"]}</td><td></td>'
        f'<td class="num">{totals["realized_pnl_eur"]}</td>'
        f'<td class="num">{totals["total_fees_eur"]}</td></tr>'
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Positions</title><style>{_STYLE}</style></head><body>"
        f"<h1>Positions</h1><table><thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody><tfoot>{footer}</tfoot>"
        "</table></body></html>"
    )


def make_server(database: str, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            with Ledger(database) as ledger:
                page = render_positions(
                    compute_holdings(ledger.list_transactions())
                )
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer((host, port), Handler)
