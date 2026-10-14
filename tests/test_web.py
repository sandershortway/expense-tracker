import threading
import urllib.error
import urllib.request
from decimal import Decimal

import pytest

from investment_ledger.domain import TransactionData
from investment_ledger.holdings import compute_holdings
from investment_ledger.storage import Ledger
from investment_ledger.valuation import Price
from investment_ledger.web import make_server, render_positions


def transaction(**overrides):
    values = {
        "side": "buy",
        "instrument_type": "etf",
        "ticker": "AEX",
        "exchange": "XAMS",
        "trade_date": "2025-03-11",
        "quantity": "2",
        "unit_price_eur": "50.00",
        "gross_amount_eur": "100.00",
        "fee_eur": "1.00",
        "name": "iShares <AEX> & Co",
    }
    values.update(overrides)
    return values


def seed(db_path, *rows):
    with Ledger(db_path) as ledger:
        stored = ledger.add_many(
            [TransactionData.from_mapping(row) for row in rows]
        )
    return stored


def test_render_positions_shows_each_position_and_totals(tmp_path):
    stored = seed(
        tmp_path / "ledger.sqlite3",
        transaction(),
        transaction(
            ticker="NVDA",
            instrument_type="stock",
            exchange="XETRA",
            name="Nvidia",
        ),
    )

    page = render_positions(compute_holdings(stored))

    assert "<h1>Positions</h1>" in page
    assert "<td>AEX</td>" in page
    assert "<td>NVDA</td>" in page
    assert "iShares &lt;AEX&gt; &amp; Co" in page
    assert "<AEX>" not in page
    assert '<td class="num">101.00</td>' in page
    assert '<td class="num">202.00</td>' in page


def test_render_positions_with_prices_shows_value_and_return(tmp_path):
    stored = seed(tmp_path / "ledger.sqlite3", transaction())
    prices = {"AEX@XAMS": Price(Decimal("60.60"), "2026-10-14", "test")}

    page = render_positions(compute_holdings(stored), prices)

    assert '<td class="num">60.60</td>' in page
    assert '<td class="num">121.20</td>' in page
    assert '<td class="num pos">+20.20</td>' in page
    assert '<td class="num pos">+20.00%</td>' in page
    assert "Prices as of 2026-10-14" in page


def test_render_positions_empty_ledger():
    page = render_positions(compute_holdings([]))

    assert "No positions" in page
    assert '<td class="num">0.00</td>' in page


@pytest.fixture
def server(tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    seed(db_path, transaction())
    server = make_server(str(db_path), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_server_returns_positions_page(server):
    with urllib.request.urlopen(server + "/") as response:
        body = response.read().decode("utf-8")
        content_type = response.headers["Content-Type"]

    assert content_type == "text/html; charset=utf-8"
    assert "<td>AEX</td>" in body


def test_server_returns_404_for_other_paths(server):
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(server + "/missing")
    assert error.value.code == 404
