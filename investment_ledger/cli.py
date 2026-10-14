from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, TextIO

from investment_ledger.domain import TransactionData, ValidationError
from investment_ledger.holdings import HoldingsReport, compute_holdings
from investment_ledger.storage import Ledger, LedgerError, TransactionNotFound

EXIT_OPERATIONAL_ERROR = 1
EXIT_INPUT_ERROR = 2
DEFAULT_DATABASE = Path(".data") / "investments.sqlite3"
ENV_DATABASE = "INVESTMENT_LEDGER_DB"


class InputError(Exception):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="investment-ledger")
    parser.add_argument("--db", help="SQLite database path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("add", help="add one transaction using prompts")
    commands.add_parser("list", help="list stored transactions")

    holdings = commands.add_parser(
        "holdings",
        help="show per-instrument positions, cost basis, and realized P&L",
    )
    holdings.add_argument(
        "--ticker",
        help="restrict output to one ticker (case-insensitive)",
    )

    edit = commands.add_parser("edit", help="edit a transaction by ID")
    edit.add_argument("transaction_id")
    for field, option in (
        ("side", "--side"),
        ("instrument_type", "--instrument-type"),
        ("ticker", "--ticker"),
        ("exchange", "--exchange"),
        ("trade_date", "--trade-date"),
        ("quantity", "--quantity"),
        ("unit_price_eur", "--unit-price-eur"),
        ("gross_amount_eur", "--gross-amount-eur"),
        ("currency", "--currency"),
    ):
        edit.add_argument(option, dest=field)
    name_group = edit.add_mutually_exclusive_group()
    name_group.add_argument("--name")
    name_group.add_argument("--clear-name", action="store_true")
    fee_group = edit.add_mutually_exclusive_group()
    fee_group.add_argument("--fee-eur")
    fee_group.add_argument("--clear-fee", action="store_true")

    delete = commands.add_parser("delete", help="delete a transaction by ID")
    delete.add_argument("transaction_id")
    delete.add_argument(
        "--yes", action="store_true", help="confirm without a prompt"
    )

    batch = commands.add_parser(
        "import", help="import a JSON array of transactions"
    )
    batch.add_argument(
        "source", help="JSON file path, or '-' to read standard input"
    )

    prepare = commands.add_parser(
        "prepare-screenshot-import",
        help="OCR transaction screenshots into reviewable import JSON",
    )
    prepare.add_argument(
        "--input-dir",
        default="data/screenshots",
        help="folder with PNG screenshots (default: data/screenshots)",
    )
    prepare.add_argument(
        "--output-dir",
        default=".data/screenshot-import",
        help="base folder for run artifacts "
        "(default: .data/screenshot-import)",
    )
    return parser


def _emit(
    value: Any, output_format: str, stream: TextIO | None = None
) -> None:
    stream = stream or sys.stdout
    if output_format == "json":
        print(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            file=stream,
        )
    elif isinstance(value, dict) and "transactions" in value:
        print(f"{value['count']} transaction(s)", file=stream)
        for transaction in value["transactions"]:
            print(
                f"{transaction['transaction_id']} "
                f"(entry {transaction['entry_order']}): "
                f"{transaction['side']} {transaction['instrument_type']} "
                f"{transaction['ticker']}@{transaction['exchange']} "
                f"name={transaction['name'] or '<none>'}",
                file=stream,
            )
            print(
                f"  date={transaction['trade_date']} "
                f"quantity={transaction['quantity']} "
                f"unit_price_eur={transaction['unit_price_eur']} "
                f"gross_amount_eur={transaction['gross_amount_eur']} "
                f"fee_eur={transaction['fee_eur'] or '<none>'} "
                f"currency={transaction['currency']}",
                file=stream,
            )
            print(
                f"  created_at={transaction['created_at']} "
                f"updated_at={transaction['updated_at']}",
                file=stream,
            )
    elif isinstance(value, dict) and "holdings" in value:
        print(f"{value['count']} holding(s)", file=stream)
        for position in value["holdings"]:
            print(
                f"{position['ticker']}@{position['exchange']} "
                f"({position['instrument_type']}) "
                f"name={position['name'] or '<none>'}",
                file=stream,
            )
            print(
                f"  net_quantity={position['net_quantity']} "
                f"cost_basis_eur={position['cost_basis_eur']} "
                f"average_cost_eur="
                f"{position['average_cost_eur'] or '<none>'}",
                file=stream,
            )
            print(
                f"  total_invested_eur={position['total_invested_eur']} "
                f"total_proceeds_eur={position['total_proceeds_eur']} "
                f"realized_pnl_eur={position['realized_pnl_eur']} "
                f"total_fees_eur={position['total_fees_eur']}",
                file=stream,
            )
            print(
                f"  transactions={position['transaction_count']} "
                f"first_trade_date={position['first_trade_date']} "
                f"last_trade_date={position['last_trade_date']}",
                file=stream,
            )
            for warning in position["warnings"]:
                print(f"  warning: {warning}", file=stream)
        totals = value["totals"]
        print(
            f"Totals: cost_basis_eur={totals['cost_basis_eur']} "
            f"total_invested_eur={totals['total_invested_eur']} "
            f"total_proceeds_eur={totals['total_proceeds_eur']} "
            f"realized_pnl_eur={totals['realized_pnl_eur']} "
            f"total_fees_eur={totals['total_fees_eur']}",
            file=stream,
        )
    elif isinstance(value, dict) and "transaction" in value:
        transaction = value["transaction"]
        print(
            f"{transaction['side'].title()} transaction "
            f"{transaction['transaction_id']} saved: "
            f"{transaction['quantity']} {transaction['ticker']}@"
            f"{transaction['exchange']} on {transaction['trade_date']} "
            f"for EUR {transaction['gross_amount_eur']}",
            file=stream,
        )
    elif isinstance(value, dict) and "error" in value:
        print(f"error: {value['error']['message']}", file=sys.stderr)
        for result in value.get("results", []):
            message = result.get("error", {}).get("message", "")
            line = f"Row {result['index']}: {result['status']} {message}"
            print(line.rstrip(), file=stream)
    elif isinstance(value, dict) and "results" in value:
        for result in value["results"]:
            status = result["status"]
            detail = result.get("transaction_id") or result.get(
                "error", {}
            ).get("message", "")
            print(
                f"Row {result['index']}: {status} {detail}".rstrip(),
                file=stream,
            )
        print(
            f"Created {value['created_count']}; "
            f"rejected or skipped {value['error_count']}",
            file=stream,
        )
    elif isinstance(value, dict) and "deleted" in value:
        status = "Deleted" if value["deleted"] else "Deletion canceled"
        print(f"{status}: {value['transaction_id']}", file=stream)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2), file=stream)


def _emit_error(
    message: str, output_format: str, *, code: str = "input_error"
) -> None:
    if output_format == "json":
        _emit({"error": {"code": code, "message": message}}, output_format)
    else:
        print(f"error: {message}", file=sys.stderr)


def _read_prompt(label: str, *, optional: bool = False) -> str:
    suffix = " (optional)" if optional else ""
    print(f"{label}{suffix}: ", end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise InputError(
            "interactive input ended before all fields were entered"
        )
    return value.rstrip("\r\n").strip()


def _prompt_transaction() -> TransactionData:
    if not sys.stdin.isatty():
        raise InputError(
            "add requires an interactive terminal; use JSON import otherwise"
        )
    values = {
        "side": _read_prompt("Side (buy/sell)"),
        "instrument_type": _read_prompt("Instrument type (stock/etf)"),
        "ticker": _read_prompt("Ticker"),
        "exchange": _read_prompt("Exchange"),
        "trade_date": _read_prompt("Trade date (YYYY-MM-DD)"),
        "quantity": _read_prompt("Quantity"),
        "unit_price_eur": _read_prompt("Unit price (EUR)"),
        "gross_amount_eur": _read_prompt("Gross amount (EUR)"),
        "fee_eur": _read_prompt("Fee (EUR)", optional=True) or None,
        "name": _read_prompt("Instrument name", optional=True) or None,
    }
    return TransactionData.from_mapping(values)


def _confirm(message: str) -> bool:
    print(f"{message} [y/N] ", end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline()
    return answer.strip().lower() in {"y", "yes"}


def _import_json(ledger: Ledger, source: str, output_format: str) -> int:
    try:
        text = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise InputError(f"could not read import source: {exc}") from exc
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"invalid JSON: {exc.msg} at line {exc.lineno}"
        ) from exc
    if not isinstance(rows, list):
        raise InputError(
            "JSON import must contain an array of transaction objects"
        )

    results: list[dict[str, Any]] = []
    candidates: list[tuple[int, TransactionData]] = []
    for index, row in enumerate(rows, start=1):
        try:
            candidates.append((index, TransactionData.from_mapping(row)))
        except ValidationError as exc:
            results.append(
                {
                    "index": index,
                    "status": "rejected",
                    "error": {"code": "validation_error", "message": str(exc)},
                }
            )

    if not sys.stdin.isatty():
        seen_keys: set[tuple[object, ...]] = set()
        duplicate_indexes: set[int] = set()
        for index, data in candidates:
            key = data.duplicate_key()
            if ledger.has_duplicate(data) or key in seen_keys:
                duplicate_indexes.add(index)
            seen_keys.add(key)
        if duplicate_indexes:
            for index, _ in candidates:
                if index in duplicate_indexes:
                    results.append(
                        {
                            "index": index,
                            "status": "rejected",
                            "error": {
                                "code": "duplicate_confirmation_required",
                                "message": "rerun interactively to confirm",
                            },
                        }
                    )
                else:
                    results.append(
                        {
                            "index": index,
                            "status": "not_imported",
                            "error": {
                                "code": "batch_aborted",
                                "message": "batch was not written because it "
                                "contains a duplicate candidate",
                            },
                        }
                    )
            results.sort(key=lambda result: result["index"])
            _emit(
                {
                    "error": {
                        "code": "duplicate_confirmation_required",
                        "message": (
                            "duplicate candidate needs a terminal; "
                            "rerun interactively to confirm"
                        ),
                    },
                    "written": 0,
                    "results": results,
                },
                output_format,
            )
            return EXIT_INPUT_ERROR

    accepted: list[tuple[int, TransactionData]] = []
    accepted_keys: set[tuple[object, ...]] = set()
    for index, data in candidates:
        duplicate = (
            ledger.has_duplicate(data) or data.duplicate_key() in accepted_keys
        )
        if duplicate and not _confirm(
            f"Row {index} appears to be a duplicate. Import it?"
        ):
            results.append(
                {
                    "index": index,
                    "status": "skipped_duplicate",
                    "error": {
                        "code": "duplicate_declined",
                        "message": "duplicate was not imported",
                    },
                }
            )
            continue
        accepted.append((index, data))
        accepted_keys.add(data.duplicate_key())

    stored = ledger.add_many([data for _, data in accepted])
    for (index, _), transaction in zip(accepted, stored, strict=True):
        results.append(
            {
                "index": index,
                "status": "created",
                "transaction_id": transaction.transaction_id,
            }
        )
    results.sort(key=lambda result: result["index"])
    error_count = sum(result["status"] != "created" for result in results)
    summary = {
        "results": results,
        "created_count": len(stored),
        "error_count": error_count,
    }
    _emit(summary, output_format)
    return EXIT_INPUT_ERROR if error_count else 0


def _dispatch(args: argparse.Namespace, ledger: Ledger) -> int:
    if args.command == "add":
        transaction = ledger.add(_prompt_transaction())
        _emit({"transaction": transaction.to_mapping()}, args.format)
        return 0

    if args.command == "list":
        transactions = [
            transaction.to_mapping()
            for transaction in ledger.list_transactions()
        ]
        _emit(
            {"count": len(transactions), "transactions": transactions},
            args.format,
        )
        return 0

    if args.command == "holdings":
        positions = compute_holdings(ledger.list_transactions()).positions
        if args.ticker:
            wanted = args.ticker.upper()
            positions = [p for p in positions if p.ticker == wanted]
        _emit(HoldingsReport(positions).to_mapping(), args.format)
        return 0

    if args.command == "edit":
        changes = {
            field: getattr(args, field)
            for field in (
                "side",
                "instrument_type",
                "ticker",
                "exchange",
                "trade_date",
                "quantity",
                "unit_price_eur",
                "gross_amount_eur",
                "currency",
                "name",
                "fee_eur",
            )
            if getattr(args, field) is not None
        }
        if args.clear_name:
            changes["name"] = None
        if args.clear_fee:
            changes["fee_eur"] = None
        if not changes:
            raise InputError("edit requires at least one field option")
        transaction = ledger.update(args.transaction_id, changes)
        _emit({"transaction": transaction.to_mapping()}, args.format)
        return 0

    if args.command == "delete":
        ledger.get(args.transaction_id)
        if not args.yes:
            if not sys.stdin.isatty():
                raise InputError(
                    "delete requires --yes without an interactive terminal"
                )
            if not _confirm(f"Delete transaction {args.transaction_id}?"):
                _emit(
                    {"deleted": False, "transaction_id": args.transaction_id},
                    args.format,
                )
                return 0
        ledger.delete(args.transaction_id)
        _emit(
            {"deleted": True, "transaction_id": args.transaction_id},
            args.format,
        )
        return 0

    if args.command == "import":
        return _import_json(ledger, args.source, args.format)

    raise InputError(f"unsupported command: {args.command}")


def _prompt_mapping(label: str) -> str | None:
    try:
        return _read_prompt(label) or None
    except InputError:
        return None


def _prepare_screenshots(args: argparse.Namespace) -> int:
    from investment_ledger.ocr import (
        OcrError,
        OcrUnavailable,
        TesseractEngine,
    )
    from investment_ledger.prepare_import import prepare_import

    try:
        engine = TesseractEngine()
    except OcrUnavailable as exc:
        _emit_error(str(exc), args.format, code="operational_error")
        return EXIT_OPERATIONAL_ERROR
    prompt = _prompt_mapping if sys.stdin.isatty() else None
    try:
        outcome = prepare_import(
            Path(args.input_dir),
            Path(args.output_dir),
            engine,
            prompt=prompt,
        )
    except (OcrError, OSError) as exc:
        _emit_error(str(exc), args.format, code="operational_error")
        return EXIT_OPERATIONAL_ERROR

    summary = outcome.summary()
    if args.format == "json":
        _emit(summary, args.format)
    else:
        print(f"Screenshot preparation run: {summary['run_dir']}")
        for status, count in sorted(summary["counts"].items()):
            print(f"  {status}: {count}")
        print(f"Transactions: {summary['transactions_file']}")
        print(f"Report: {summary['report_file']}")
        print("Review the JSON, then import it with:")
        print(f"  {summary['import_command']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare-screenshot-import":
        return _prepare_screenshots(args)
    database = args.db or os.environ.get(ENV_DATABASE) or str(DEFAULT_DATABASE)
    try:
        with Ledger(database) as ledger:
            return _dispatch(args, ledger)
    except (ValidationError, TransactionNotFound, InputError) as exc:
        _emit_error(str(exc), args.format)
        return EXIT_INPUT_ERROR
    except (LedgerError, OSError, sqlite3.Error) as exc:
        _emit_error(str(exc), args.format, code="operational_error")
        return EXIT_OPERATIONAL_ERROR
