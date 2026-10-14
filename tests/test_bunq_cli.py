import io
import json

from investment_ledger import cli
from investment_ledger.storage import Ledger


class TerminalInput(io.StringIO):
    def isatty(self):
        return True


def order(**overrides):
    values = {
        "entry_id": "bunq-001",
        "order_id": None,
        "asset": "AEX",
        "name": "AEX short label",
        "legal_name": "iShares AEX UCITS ETF",
        "isin": "IE00B0M62Y33",
        "side": "buy",
        "status": "completed",
        "date_local": "2025-03-11T08:31:00",
        "timezone": None,
        "quantity": "1.09",
        "unit_price": "91.52",
        "currency": "EUR",
        "fees": "0.00",
        "total": "100.00",
        "source_url": "https://example.invalid/orders/bunq-001",
    }
    values.update(overrides)
    return values


def source_file(path, *orders):
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "export_date": "2026-10-14",
                "coverage": {"order_count": len(orders)},
                "orders": list(orders),
            }
        ),
        encoding="utf-8",
    )
    return path


def invoke(monkeypatch, capsys, db_path, *args, stdin=None):
    monkeypatch.setattr(cli.sys, "stdin", stdin or io.StringIO(""))
    code = cli.main(["--db", str(db_path), *args])
    return code, capsys.readouterr()


def test_prepare_bunq_prompts_once_and_imports_via_existing_cli(
    monkeypatch, capsys, tmp_path
):
    source = source_file(
        tmp_path / "bunq.json",
        order(entry_id="one"),
        order(
            entry_id="two",
            date_local="2025-03-12T08:31:00",
            quantity="1.00",
            total="91.52",
        ),
    )
    db_path = tmp_path / "ledger.sqlite3"
    output_dir = tmp_path / "runs"

    code, prepared = invoke(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "prepare-bunq-import",
        str(source),
        "--output-dir",
        str(output_dir),
        stdin=TerminalInput("etf\nAEX\nXAMS\n"),
    )

    summary = json.loads(prepared.out)
    rows = json.loads(
        open(summary["transactions_file"], encoding="utf-8").read()
    )
    report = json.loads(open(summary["report_file"], encoding="utf-8").read())
    assert code == 0
    assert prepared.err.count("Instrument mapping for ISIN") == 1
    assert len(rows) == 2
    assert rows[0]["name"] == "AEX short label"
    assert rows[0]["gross_amount_eur"] == "99.76"
    assert report["results"][0]["source"]["legal_name"] == (
        "iShares AEX UCITS ETF"
    )
    assert not db_path.exists()

    code, imported = invoke(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "import",
        summary["transactions_file"],
    )
    assert code == 0
    assert json.loads(imported.out)["created_count"] == 2
    with Ledger(db_path) as ledger:
        assert len(ledger.list_transactions()) == 2


def test_prepare_bunq_noninteractive_reports_missing_mapping_without_db(
    monkeypatch, capsys, tmp_path
):
    source = source_file(tmp_path / "bunq.json", order())
    db_path = tmp_path / "ledger.sqlite3"

    code, captured = invoke(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "prepare-bunq-import",
        str(source),
        "--output-dir",
        str(tmp_path / "runs"),
    )

    summary = json.loads(captured.out)
    report = json.loads(open(summary["report_file"], encoding="utf-8").read())
    assert code == 0
    assert summary["counts"] == {"needs_review": 1}
    assert "interactive terminal" in report["results"][0]["reason"]
    assert not db_path.exists()


def test_malformed_bunq_export_fails_before_artifact_or_database_creation(
    monkeypatch, capsys, tmp_path
):
    source = tmp_path / "bad.json"
    source.write_text('{"schema_version":"2.0","orders":[]}', "utf-8")
    output_dir = tmp_path / "runs"
    db_path = tmp_path / "ledger.sqlite3"

    code, captured = invoke(
        monkeypatch,
        capsys,
        db_path,
        "--format",
        "json",
        "prepare-bunq-import",
        str(source),
        "--output-dir",
        str(output_dir),
    )

    assert code == cli.EXIT_INPUT_ERROR
    assert json.loads(captured.out)["error"]["code"] == "input_error"
    assert not output_dir.exists()
    assert not db_path.exists()


def test_prepare_bunq_text_output_prints_quoted_import_path(
    monkeypatch, capsys, tmp_path
):
    source = source_file(tmp_path / "bunq.json", order())
    output_dir = tmp_path / "output with spaces"

    code, captured = invoke(
        monkeypatch,
        capsys,
        tmp_path / "db.sqlite3",
        "prepare-bunq-import",
        str(source),
        "--output-dir",
        str(output_dir),
        stdin=TerminalInput("etf\nAEX\nXAMS\n"),
    )

    assert code == 0
    assert "Review the JSON, then import it with:" in captured.out
    assert 'import "' in captured.out
    assert '"' in captured.out
