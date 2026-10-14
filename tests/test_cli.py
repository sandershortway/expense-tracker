import io
import json

from investment_ledger import cli
from investment_ledger.domain import TransactionData
from investment_ledger.storage import Ledger


class TerminalInput(io.StringIO):
    def isatty(self):
        return True


def transaction(**overrides):
    values = {
        "side": "buy",
        "instrument_type": "stock",
        "ticker": "ACME",
        "exchange": "XNAS",
        "trade_date": "2024-01-02",
        "quantity": "2.5",
        "unit_price_eur": "4.00",
        "gross_amount_eur": "10.00",
        "fee_eur": None,
        "name": "Acme Corp",
    }
    values.update(overrides)
    return values


def run_cli(monkeypatch, capsys, db_path, *args, stdin=None):
    monkeypatch.setattr(cli.sys, "stdin", stdin or io.StringIO(""))
    code = cli.main(["--db", str(db_path), *args])
    captured = capsys.readouterr()
    return code, captured


def test_prompted_add_and_json_list(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    input_values = "\n".join(
        [
            "buy",
            "stock",
            " acme ",
            "xnas",
            "2024-01-02",
            "2.5",
            "4.00",
            "10.00",
            "",
            "Acme Corp",
            "",
        ]
    )
    code, added = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "add",
        stdin=TerminalInput(input_values),
    )
    created = json.loads(added.out)["transaction"]

    assert code == 0
    assert created["ticker"] == "ACME"
    assert added.err.startswith("Side")

    code, listed = run_cli(
        monkeypatch, capsys, db_path, "--format", "json", "list"
    )
    output = json.loads(listed.out)
    assert code == 0
    assert output["count"] == 1
    assert (
        output["transactions"][0]["transaction_id"]
        == created["transaction_id"]
    )


def test_human_list_displays_all_persisted_fields(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    with Ledger(db_path) as ledger:
        ledger.add(TransactionData.from_mapping(transaction()))

    code, captured = run_cli(monkeypatch, capsys, db_path, "list")

    assert code == 0
    for field in (
        "entry",
        "stock",
        "name=Acme Corp",
        "date=2024-01-02",
        "unit_price_eur=4.00",
        "gross_amount_eur=10.00",
        "fee_eur=<none>",
        "currency=EUR",
        "created_at=",
        "updated_at=",
    ):
        assert field in captured.out


def test_add_requires_tty(monkeypatch, capsys, tmp_path):
    code, captured = run_cli(
        monkeypatch, capsys, tmp_path / "ledger.sqlite3", "add"
    )

    assert code == cli.EXIT_INPUT_ERROR
    assert "interactive terminal" in captured.err


def test_json_import_saves_valid_rows_and_reports_invalid_rows(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    source = tmp_path / "trades.json"
    source.write_text(
        json.dumps([transaction(), transaction(side="hold")]), encoding="utf-8"
    )

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        str(source),
    )

    report = json.loads(captured.out)
    assert code == cli.EXIT_INPUT_ERROR
    assert report["created_count"] == 1
    assert report["results"][0]["status"] == "created"
    assert report["results"][1]["status"] == "rejected"
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 1


def test_import_accepts_json_from_standard_input(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        "-",
        stdin=io.StringIO(json.dumps([transaction()])),
    )

    assert code == 0
    assert json.loads(captured.out)["created_count"] == 1
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 1


def test_import_reports_malformed_json(monkeypatch, capsys, tmp_path):
    source = tmp_path / "malformed.json"
    source.write_text("[", encoding="utf-8")

    code, captured = run_cli(
        monkeypatch,
        capsys,
        tmp_path / "ledger.sqlite3",
        "--format",
        "json",
        "import",
        str(source),
    )

    assert code == cli.EXIT_INPUT_ERROR
    assert json.loads(captured.out)["error"]["code"] == "input_error"


def test_duplicate_within_batch_requires_confirmation(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    source = tmp_path / "duplicates.json"
    source.write_text(
        json.dumps([transaction(), transaction()]), encoding="utf-8"
    )

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        str(source),
        stdin=TerminalInput("n\n"),
    )

    report = json.loads(captured.out)
    assert code == cli.EXIT_INPUT_ERROR
    assert [row["status"] for row in report["results"]] == [
        "created",
        "skipped_duplicate",
    ]
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 1


def test_noninteractive_duplicate_fails_before_any_batch_writes(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    with Ledger(db_path) as ledger:
        original = ledger.add(TransactionData.from_mapping(transaction()))
    source = tmp_path / "trades.json"
    source.write_text(
        json.dumps([transaction(), transaction(ticker="OTHER")]),
        encoding="utf-8",
    )

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        str(source),
    )

    report = json.loads(captured.out)
    assert code == cli.EXIT_INPUT_ERROR
    assert report["written"] == 0
    assert report["results"][0]["status"] == "rejected"
    assert report["results"][1]["status"] == "not_imported"
    with Ledger(db_path) as ledger:
        assert [tx.transaction_id for tx in ledger.list_transactions()] == [
            original.transaction_id
        ]


def test_interactive_duplicate_requires_confirmation(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    with Ledger(db_path) as ledger:
        ledger.add(TransactionData.from_mapping(transaction()))
    source = tmp_path / "trades.json"
    source.write_text(json.dumps([transaction()]), encoding="utf-8")

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        str(source),
        stdin=TerminalInput("y\n"),
    )

    assert code == 0
    assert json.loads(captured.out)["created_count"] == 1
    assert "appears to be a duplicate" in captured.err
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 2


def test_declined_duplicate_skips_row_and_returns_error(
    monkeypatch, capsys, tmp_path
):
    db_path = tmp_path / "ledger.sqlite3"
    with Ledger(db_path) as ledger:
        ledger.add(TransactionData.from_mapping(transaction()))
    source = tmp_path / "trades.json"
    source.write_text(json.dumps([transaction()]), encoding="utf-8")

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        str(source),
        stdin=TerminalInput("n\n"),
    )

    assert code == cli.EXIT_INPUT_ERROR
    assert (
        json.loads(captured.out)["results"][0]["status"] == "skipped_duplicate"
    )
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 1


def test_edit_and_confirmed_delete_persist(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    with Ledger(db_path) as ledger:
        created = ledger.add(TransactionData.from_mapping(transaction()))

    code, edited = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "edit",
        created.transaction_id,
        "--name",
        "Updated name",
    )
    assert code == 0
    assert json.loads(edited.out)["transaction"]["name"] == "Updated name"

    code, deleted = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "delete",
        created.transaction_id,
        "--yes",
    )
    assert code == 0
    assert json.loads(deleted.out)["deleted"] is True
    with Ledger(db_path) as ledger:
        assert ledger.list_transactions() == []


def test_environment_database_override(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "from-env.sqlite3"
    monkeypatch.setenv(cli.ENV_DATABASE, str(db_path))
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(""))

    code = cli.main(["--format", "json", "list"])

    assert code == 0
    assert db_path.exists()
    assert json.loads(capsys.readouterr().out)["transactions"] == []


def _seed(db_path, *rows):
    with Ledger(str(db_path)) as ledger:
        ledger.add_many([TransactionData.from_mapping(row) for row in rows])


def test_holdings_text_output(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    _seed(
        db_path,
        transaction(
            ticker="NVDA",
            name="Nvidia",
            quantity="10",
            unit_price_eur="100.00",
            gross_amount_eur="1000.00",
            fee_eur="5.00",
        ),
        transaction(
            side="sell",
            ticker="NVDA",
            name="Nvidia",
            trade_date="2024-02-01",
            quantity="5",
            unit_price_eur="120.00",
            gross_amount_eur="600.00",
        ),
    )

    code, captured = run_cli(monkeypatch, capsys, db_path, "holdings")

    assert code == 0
    assert "1 holding(s)" in captured.out
    assert "NVDA@XNAS (stock) name=Nvidia" in captured.out
    assert "net_quantity=5" in captured.out
    assert "cost_basis_eur=502.50" in captured.out
    assert "average_cost_eur=100.500000" in captured.out
    assert "realized_pnl_eur=97.50" in captured.out
    assert "total_fees_eur=5.00" in captured.out
    assert "transactions=2" in captured.out
    assert "Totals:" in captured.out
    assert "cost_basis_eur=502.50" in captured.out


def test_holdings_json_output_and_ticker_filter(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    _seed(
        db_path,
        transaction(ticker="NVDA", name="Nvidia"),
        transaction(
            ticker="SXRV",
            instrument_type="etf",
            name="S&P 500 Technology",
        ),
    )

    code, captured = run_cli(
        monkeypatch, capsys, db_path, "--format", "json", "holdings"
    )
    output = json.loads(captured.out)
    assert code == 0
    assert output["count"] == 2
    tickers = [p["ticker"] for p in output["holdings"]]
    assert tickers == ["NVDA", "SXRV"]
    assert output["holdings"][0]["cost_basis_eur"] == "10.00"
    assert output["holdings"][0]["warnings"] == []
    assert set(output["totals"]) == {
        "cost_basis_eur",
        "total_invested_eur",
        "total_proceeds_eur",
        "realized_pnl_eur",
        "total_fees_eur",
    }

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "holdings",
        "--ticker",
        "nvda",
    )
    output = json.loads(captured.out)
    assert code == 0
    assert output["count"] == 1
    assert output["holdings"][0]["ticker"] == "NVDA"

    code, captured = run_cli(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "holdings",
        "--ticker",
        "MISSING",
    )
    output = json.loads(captured.out)
    assert code == 0
    assert output["count"] == 0
    assert output["holdings"] == []
    assert output["totals"]["cost_basis_eur"] == "0.00"


def test_holdings_empty_ledger(monkeypatch, capsys, tmp_path):
    code, captured = run_cli(
        monkeypatch, capsys, tmp_path / "ledger.sqlite3", "holdings"
    )
    assert code == 0
    assert "0 holding(s)" in captured.out
    assert "cost_basis_eur=0.00" in captured.out


def test_holdings_oversell_warning_shown(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    _seed(
        db_path,
        transaction(
            side="sell",
            quantity="8",
            unit_price_eur="4.00",
            gross_amount_eur="32.00",
        ),
    )
    code, captured = run_cli(monkeypatch, capsys, db_path, "holdings")
    assert code == 0
    assert "warning: sold 8 more than held" in captured.out


def test_holdings_does_not_mutate_ledger(monkeypatch, capsys, tmp_path):
    db_path = tmp_path / "ledger.sqlite3"
    _seed(db_path, transaction())

    run_cli(monkeypatch, capsys, db_path, "holdings")

    with Ledger(str(db_path)) as ledger:
        assert len(ledger.list_transactions()) == 1
