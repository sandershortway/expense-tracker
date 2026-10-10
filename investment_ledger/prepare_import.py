"""Prepare reviewable import JSON from transaction screenshots.

The command scans a folder of screenshots, parses each one, asks for a
session-only instrument mapping, and writes ``transactions.json`` plus
``report.json`` under a unique run directory. It never touches the
SQLite ledger: importing stays a separate explicit user action.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from investment_ledger.domain import ValidationError
from investment_ledger.ocr import OcrError
from investment_ledger.screenshot import (
    InstrumentMapping,
    OcrEngine,
    ParsedScreenshot,
    parse_screenshot,
)

if TYPE_CHECKING:
    from PIL import Image

DEFAULT_INPUT_DIR = Path("data") / "screenshots"
DEFAULT_OUTPUT_DIR = Path(".data") / "screenshot-import"
DIVIDEND_PREFIX = "dividend_"
SUPPORTED_SUFFIXES = {".png"}
DONE_DIR = "done"

PromptFn = Callable[[str], "str | None"]
ParseFn = Callable[["Image.Image", "Engine"], ParsedScreenshot]


class Engine(OcrEngine, Protocol):
    """OCR engine plus the image loader the pipeline needs."""

    def load(self, path: str | Path) -> Image.Image: ...


@dataclass
class PrepareOutcome:
    run_dir: Path
    transactions_path: Path
    report_path: Path
    transactions: list[dict]
    report: list[dict]
    moved: dict[str, str]
    renamed: dict[str, str]

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.report:
            status = entry["status"]
            counts[status] = counts.get(status, 0) + 1
        return counts

    def summary(self) -> dict:
        return {
            "run_dir": str(self.run_dir),
            "transactions_file": str(self.transactions_path),
            "report_file": str(self.report_path),
            "counts": self.counts,
            "import_command": import_command(self.transactions_path),
        }


def import_command(transactions_path: Path) -> str:
    return (
        "uv run python -m investment_ledger --format json import "
        f'"{transactions_path}"'
    )


def _new_run_dir(base: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = base / f"run-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _scan(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise OSError(f"input directory not found: {input_dir}")
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and not path.name.lower().startswith(DIVIDEND_PREFIX)
    )


def resolve_mapping(
    label: str,
    cache: dict[str, InstrumentMapping | None],
    prompt: PromptFn | None,
) -> InstrumentMapping | None:
    """Prompt once per product label, reusing the answer this run."""
    if label in cache:
        return cache[label]
    mapping = None
    if prompt is not None:
        instrument_type = prompt(f"Instrument type for '{label}' (stock/etf)")
        ticker = prompt(f"Ticker for '{label}'")
        exchange = prompt(f"Exchange for '{label}'")
        if (
            instrument_type
            and ticker
            and exchange
            and instrument_type.lower() in {"stock", "etf"}
        ):
            mapping = InstrumentMapping(
                instrument_type.lower(), ticker.upper(), exchange.upper()
            )
    cache[label] = mapping
    return mapping


def _extracted(parsed: ParsedScreenshot) -> dict:
    def text(value: Decimal | None) -> str | None:
        return None if value is None else str(value)

    return {
        "product_name": parsed.product_name,
        "trade_date": (
            None
            if parsed.trade_date is None
            else parsed.trade_date.isoformat()
        ),
        "trade_time": parsed.trade_time,
        "gross_amount_eur": text(parsed.gross_amount_eur),
        "displayed_quantity": text(parsed.displayed_quantity),
        "derived_quantity": text(parsed.derived_quantity),
        "unit_price_eur": text(parsed.unit_price_eur),
        "fee_eur": text(parsed.fee_eur),
    }


def _process_file(
    path: Path,
    engine: Engine,
    parse_fn: ParseFn,
    mappings: dict[str, InstrumentMapping | None],
    prompt: PromptFn | None,
    transactions: list[dict],
) -> dict:
    entry: dict = {"source": path.name}
    try:
        image = engine.load(path)
    except OcrError as exc:
        entry.update(
            status="error",
            classification="unknown",
            reason=f"image could not be read: {exc}",
        )
        return entry
    try:
        parsed = parse_fn(image, engine)
    except OcrError as exc:
        entry.update(
            status="error",
            classification="unknown",
            reason=f"OCR failed: {exc}",
        )
        return entry
    entry["classification"] = parsed.event or "unknown"
    entry["extracted"] = _extracted(parsed)
    entry["min_word_confidence"] = parsed.min_confidence
    entry["warnings"] = parsed.warnings
    if parsed.problems:
        entry["problems"] = parsed.problems

    if parsed.event == "dividend":
        entry["status"] = "dividend"
        if parsed.product_name is None:
            entry["status"] = "needs_review"
            entry["reason"] = (
                "dividend recognised but the instrument name "
                "could not be identified"
            )
        return entry

    if parsed.event != "purchase" or not parsed.ready:
        entry["status"] = "needs_review"
        entry["reason"] = "; ".join(parsed.problems) or (
            "not a purchase screenshot"
        )
        return entry

    label = parsed.product_name or ""
    mapping = resolve_mapping(label, mappings, prompt)
    if mapping is None:
        entry["status"] = "needs_review"
        entry["reason"] = f"no instrument mapping supplied for '{label}'"
        return entry
    entry["mapping"] = {
        "instrument_type": mapping.instrument_type,
        "ticker": mapping.ticker,
        "exchange": mapping.exchange,
    }
    try:
        row = parsed.import_row(mapping)
    except ValidationError as exc:
        entry["status"] = "needs_review"
        entry["reason"] = f"transaction validation failed: {exc}"
        return entry
    transactions.append(row)
    entry["status"] = "ready"
    return entry


def prepare_import(
    input_dir: Path,
    output_dir: Path,
    engine: Engine,
    *,
    prompt: PromptFn | None = None,
    parse_fn: ParseFn = parse_screenshot,
) -> PrepareOutcome:
    """Run the full preparation pipeline and write the run artifacts."""
    files = _scan(input_dir)
    transactions: list[dict] = []
    report: list[dict] = []
    mappings: dict[str, InstrumentMapping | None] = {}
    ready_paths: list[Path] = []
    dividend_paths: list[Path] = []

    for path in files:
        entry = _process_file(
            path, engine, parse_fn, mappings, prompt, transactions
        )
        if entry["status"] == "ready":
            ready_paths.append(path)
        elif entry["status"] == "dividend":
            dividend_paths.append(path)
        report.append(entry)

    run_dir = _new_run_dir(output_dir)
    transactions_path = run_dir / "transactions.json"
    report_path = run_dir / "report.json"
    transactions_path.write_text(
        json.dumps(transactions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    moved, renamed = _organise(input_dir, ready_paths, dividend_paths, report)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PrepareOutcome(
        run_dir=run_dir,
        transactions_path=transactions_path,
        report_path=report_path,
        transactions=transactions,
        report=report,
        moved=moved,
        renamed=renamed,
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return slug or "INSTRUMENT"


def _unique_destination(directory: Path, name: str) -> Path:
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _next_dividend_name(directory: Path, slug: str) -> str:
    highest = 0
    pattern = re.compile(
        rf"^{re.escape(DIVIDEND_PREFIX + slug)}_(\d+)\.png\Z",
        re.IGNORECASE,
    )
    for path in directory.glob(f"{DIVIDEND_PREFIX}{slug}_*.png"):
        match = pattern.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{DIVIDEND_PREFIX}{slug}_{highest + 1:03d}.png"


def _organise(
    input_dir: Path,
    ready_paths: list[Path],
    dividend_paths: list[Path],
    report: list[dict],
) -> tuple[dict[str, str], dict[str, str]]:
    """Move ready purchases and rename dividends after artifacts exist."""
    by_source = {entry["source"]: entry for entry in report}
    moved: dict[str, str] = {}
    renamed: dict[str, str] = {}

    done_dir = input_dir / DONE_DIR
    if ready_paths:
        done_dir.mkdir(exist_ok=True)
    for path in ready_paths:
        entry = by_source[path.name]
        try:
            destination = _unique_destination(done_dir, path.name)
            path.replace(destination)
        except OSError as exc:
            entry["warnings"].append(
                f"file stayed in place; move to {DONE_DIR}/ failed: {exc}"
            )
            entry["move_error"] = str(exc)
            continue
        moved[path.name] = str(destination)
        entry["destination"] = str(destination)

    for path in dividend_paths:
        entry = by_source[path.name]
        product_name = entry["extracted"].get("product_name") or ""
        try:
            name = _next_dividend_name(input_dir, _slug(product_name))
            destination = _unique_destination(input_dir, name)
            path.replace(destination)
        except OSError as exc:
            entry["warnings"].append(
                f"dividend recognised but could not be renamed: {exc}"
            )
            entry["rename_error"] = str(exc)
            continue
        renamed[path.name] = destination.name
        entry["destination"] = destination.name

    return moved, renamed
