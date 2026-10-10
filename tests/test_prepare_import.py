import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from investment_ledger.domain import TransactionData
from investment_ledger.prepare_import import (
    PrepareOutcome,
    import_command,
    prepare_import,
)
from investment_ledger.screenshot import ParsedScreenshot


class FakeEngine:
    """Only `load` is exercised; parse results are injected."""

    def load(self, path):
        return path


def _parser(results: dict[str, ParsedScreenshot]):
    def parse(image, engine):
        return results[image.name]

    return parse


def _purchase(name: str = "Nvidia", problems=None) -> ParsedScreenshot:
    return ParsedScreenshot(
        event="purchase",
        product_name=name,
        trade_date=date(2025, 3, 11),
        trade_time="08:33",
        gross_amount_eur=Decimal("100.00"),
        displayed_quantity=Decimal("1.03"),
        unit_price_eur=Decimal("96.82"),
        fee_eur=Decimal("0.00"),
        derived_quantity=Decimal("1.03284445"),
        problems=problems or [],
    )


def _dividend(name: str = "Nvidia") -> ParsedScreenshot:
    return ParsedScreenshot(
        event="dividend",
        product_name=name,
        trade_date=date(2026, 10, 2),
        trade_time="15:35",
        gross_amount_eur=Decimal("2.07"),
    )


def _prompt_for(ticker: str = "NVDA", exchange: str = "XETRA"):
    calls = []

    def prompt(label: str):
        calls.append(label)
        if "type" in label.lower():
            return "stock"
        if "ticker" in label.lower():
            return ticker
        return exchange

    return prompt, calls


def _touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_bytes(b"png")


def test_prepare_writes_transactions_and_report(tmp_path) -> None:
    input_dir = tmp_path / "screens"
    input_dir.mkdir()
    _touch(
        input_dir,
        "buy1.png",
        "buy2.png",
        "div.png",
        "dividend_old_001.png",
        "note.txt",
        "weird.png",
    )
    (input_dir / "done").mkdir()
    _touch(input_dir / "done", "skip.png")
    results = {
        "buy1.png": _purchase(),
        "buy2.png": _purchase(),
        "div.png": _dividend(),
        "weird.png": ParsedScreenshot(
            event="purchase",
            product_name="Nvidia",
            problems=["amount: could not parse 'abc'"],
        ),
    }
    prompt, calls = _prompt_for()
    outcome = prepare_import(
        input_dir,
        tmp_path / "runs",
        FakeEngine(),
        prompt=prompt,
        parse_fn=_parser(results),
    )

    transactions = json.loads(outcome.transactions_path.read_text())
    assert len(transactions) == 2
    for row in transactions:
        TransactionData.from_mapping(row)
        assert set(row) == {
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
        assert isinstance(row["quantity"], str)
        assert row["side"] == "buy"

    report = json.loads(outcome.report_path.read_text())
    assert len(report) == 4  # dividend_* prefix and done/ are skipped
    by_source = {entry["source"]: entry for entry in report}
    assert by_source["buy1.png"]["status"] == "ready"
    assert by_source["buy2.png"]["status"] == "ready"
    assert by_source["div.png"]["status"] == "dividend"
    assert by_source["weird.png"]["status"] == "needs_review"
    assert "amount" in by_source["weird.png"]["reason"]

    extracted = by_source["buy1.png"]["extracted"]
    assert extracted["displayed_quantity"] == "1.03"
    assert extracted["derived_quantity"] == "1.03284445"
    assert by_source["buy1.png"]["mapping"]["ticker"] == "NVDA"

    # The same product label is mapped only once per invocation.
    type_prompts = [c for c in calls if "type" in c.lower()]
    assert len(type_prompts) == 1


def test_run_directories_are_unique(tmp_path) -> None:
    input_dir = tmp_path / "screens"
    input_dir.mkdir()
    _touch(input_dir, "buy.png")
    results = {"buy.png": _purchase()}
    prompt, _ = _prompt_for()
    first = prepare_import(
        input_dir,
        tmp_path / "r",
        FakeEngine(),
        prompt=prompt,
        parse_fn=_parser(results),
    )
    second = prepare_import(
        input_dir,
        tmp_path / "r",
        FakeEngine(),
        prompt=prompt,
        parse_fn=_parser(results),
    )
    assert first.run_dir != second.run_dir
    assert first.run_dir.is_dir() and second.run_dir.is_dir()


def test_declined_mapping_marks_review(tmp_path) -> None:
    input_dir = tmp_path / "screens"
    input_dir.mkdir()
    _touch(input_dir, "buy.png")
    results = {"buy.png": _purchase()}
    outcome = prepare_import(
        input_dir,
        tmp_path / "r",
        FakeEngine(),
        prompt=lambda label: None,
        parse_fn=_parser(results),
    )
    assert json.loads(outcome.transactions_path.read_text()) == []
    report = json.loads(outcome.report_path.read_text())
    assert report[0]["status"] == "needs_review"
    assert "mapping" in report[0]["reason"]


def test_missing_input_dir_raises(tmp_path) -> None:
    import pytest

    with pytest.raises(OSError):
        prepare_import(tmp_path / "missing", tmp_path / "r", FakeEngine())


def test_import_command_is_powershell_ready(tmp_path) -> None:
    path = Path(r".data\screenshot-import\run-x\transactions.json")
    command = import_command(path)
    assert command == (
        f'uv run python -m investment_ledger --format json import "{path}"'
    )
    assert command.count('"') == 2


def test_empty_input_produces_empty_artifacts(tmp_path) -> None:
    input_dir = tmp_path / "screens"
    input_dir.mkdir()
    outcome = prepare_import(input_dir, tmp_path / "r", FakeEngine())
    assert json.loads(outcome.transactions_path.read_text()) == []
    assert json.loads(outcome.report_path.read_text()) == []
    assert outcome.counts == {}
    assert isinstance(outcome, PrepareOutcome)
