import json
from pathlib import Path

import pytest

from investment_ledger.prepare_bunq_import import prepare_bunq_import


def order(**overrides):
    values = {
        "entry_id": "bunq-001",
        "order_id": None,
        "asset": "AEX",
        "name": "AEX Short Name",
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


def source_file(directory: Path, *orders):
    path = directory / "orders.json"
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


def mapping_prompt(calls, *, invalid_isins=()):
    def prompt(isin):
        calls.append(isin)
        if isin in invalid_isins:
            return ("crypto", "BAD", "XAMS")
        return ("etf", "AEX", "XAMS")

    return prompt


def test_prepares_reviewable_artifacts_and_prompts_once_per_isin(tmp_path):
    input_path = source_file(
        tmp_path,
        order(entry_id="one"),
        order(entry_id="two"),
        order(
            entry_id="other",
            isin="IE00BGV5VN51",
            asset="AI & Big Data",
            name="AI & Big Data",
        ),
    )
    original_text = input_path.read_text(encoding="utf-8")
    calls = []

    outcome = prepare_bunq_import(
        input_path,
        tmp_path / "output with spaces",
        prompt=mapping_prompt(calls),
    )

    transactions = json.loads(outcome.transactions_path.read_text("utf-8"))
    report = json.loads(outcome.report_path.read_text("utf-8"))
    assert calls == ["IE00B0M62Y33", "IE00BGV5VN51"]
    assert len(transactions) == 3
    assert report["counts"] == {"ready": 3}
    assert [row["entry_id"] for row in report["results"]] == [
        "one",
        "two",
        "other",
    ]
    assert transactions[0]["gross_amount_eur"] == "99.76"
    assert transactions[0]["quantity"] == "1.09"
    assert report["results"][0]["difference_eur"] == "-0.24"
    assert report["results"][0]["warnings"]
    assert input_path.read_text(encoding="utf-8") == original_text
    assert '"' in outcome.import_command
    assert str(outcome.transactions_path) in outcome.import_command
    assert not (tmp_path / "investments.sqlite3").exists()


def test_missing_mapping_produces_empty_import_and_actionable_report(tmp_path):
    input_path = source_file(tmp_path, order())

    outcome = prepare_bunq_import(input_path, tmp_path / "output")

    assert json.loads(outcome.transactions_path.read_text("utf-8")) == []
    report = json.loads(outcome.report_path.read_text("utf-8"))
    assert report["counts"] == {"needs_review": 1}
    assert "interactive terminal" in report["results"][0]["reason"]


def test_declined_and_invalid_mapping_are_reported_per_isin(tmp_path):
    input_path = source_file(
        tmp_path,
        order(entry_id="declined"),
        order(entry_id="invalid", isin="IE00BGV5VN51"),
    )

    outcome = prepare_bunq_import(
        input_path,
        tmp_path / "output",
        prompt=lambda isin: (
            None if isin == "IE00B0M62Y33" else ("invalid", "BAD", "XAMS")
        ),
    )

    report = json.loads(outcome.report_path.read_text("utf-8"))
    assert report["counts"] == {"needs_review": 2}
    assert "not provided" in report["results"][0]["reason"]
    assert "invalid instrument mapping" in report["results"][1]["reason"]


def test_invalid_order_does_not_block_valid_order(tmp_path):
    input_path = source_file(
        tmp_path,
        order(entry_id="ready"),
        order(entry_id="invalid", currency="USD"),
    )

    outcome = prepare_bunq_import(
        input_path,
        tmp_path / "output",
        prompt=lambda _: ("etf", "AEX", "XAMS"),
    )

    assert len(json.loads(outcome.transactions_path.read_text("utf-8"))) == 1
    report = json.loads(outcome.report_path.read_text("utf-8"))
    assert report["counts"] == {"ready": 1, "rejected": 1}
    assert report["results"][1]["entry_id"] == "invalid"
    assert report["results"][1]["status"] == "rejected"


def test_malformed_envelope_writes_no_artifacts(tmp_path):
    input_path = tmp_path / "bad.json"
    input_path.write_text('{"schema_version":"2.0","orders":[]}', "utf-8")
    output_dir = tmp_path / "output"

    with pytest.raises(ValueError, match="unsupported Bunq schema_version"):
        prepare_bunq_import(input_path, output_dir)

    assert not output_dir.exists()


def test_each_preparation_run_has_unique_artifacts(tmp_path):
    input_path = source_file(tmp_path, order())
    output = tmp_path / "runs"

    def prompt(_):
        return ("etf", "AEX", "XAMS")

    first = prepare_bunq_import(input_path, output, prompt=prompt)
    second = prepare_bunq_import(input_path, output, prompt=prompt)

    assert first.run_dir != second.run_dir
    assert first.transactions_path.exists()
    assert second.transactions_path.exists()
    assert len(list(output.glob("run-*/transactions.json"))) == 2
