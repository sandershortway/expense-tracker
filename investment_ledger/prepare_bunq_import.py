from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from investment_ledger.bunq_import import (
    BunqImportError,
    InstrumentMapping,
    parse_bunq_export,
)
from investment_ledger.domain import ValidationError

MappingPrompt = Callable[[str], tuple[str, str, str] | None]


class PrepareOutcome:
    def __init__(
        self,
        run_dir: Path,
        transactions_path: Path,
        report_path: Path,
        counts: dict[str, int],
        import_command: str,
    ) -> None:
        self.run_dir = run_dir
        self.transactions_path = transactions_path
        self.report_path = report_path
        self.counts = counts
        self.import_command = import_command

    def summary(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "transactions_file": str(self.transactions_path),
            "report_file": str(self.report_path),
            "counts": self.counts,
            "import_command": self.import_command,
        }


def _powershell_quote(value: str) -> str:
    escaped = value.replace("`", "``").replace('"', '`"')
    return f'"{escaped}"'


def prepare_bunq_import(
    source_path: Path,
    output_dir: Path,
    *,
    prompt: MappingPrompt | None = None,
) -> PrepareOutcome:
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BunqImportError(f"could not read Bunq export: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BunqImportError(
            f"invalid Bunq JSON: {exc.msg} at line {exc.lineno}"
        ) from exc
    parsed = parse_bunq_export(document)

    mappings: dict[str, InstrumentMapping] = {}
    mapping_errors: dict[str, str] = {}
    for isin in parsed.isins:
        if prompt is None:
            mapping_errors[isin] = "mapping requires an interactive terminal"
            continue
        values = prompt(isin)
        if values is None:
            mapping_errors[isin] = "instrument mapping was not provided"
            continue
        try:
            mappings[isin] = InstrumentMapping.from_values(*values)
        except (TypeError, ValidationError) as exc:
            mapping_errors[isin] = f"invalid instrument mapping: {exc}"

    transactions, results = parsed.transactions(mappings, mapping_errors)
    counts = dict(Counter(result["status"] for result in results))
    report = {
        "source_file": source_path.name,
        "schema_version": parsed.schema_version,
        "export_date": parsed.export_date,
        "coverage": parsed.coverage,
        "counts": counts,
        "results": results,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = (
        f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    )
    run_dir = output_dir / run_id
    if run_dir.exists():
        raise OSError(f"Bunq import run directory already exists: {run_dir}")

    with tempfile.TemporaryDirectory(
        prefix=".bunq-stage-", dir=output_dir
    ) as staging:
        staging_dir = Path(staging)
        transactions_path = staging_dir / "transactions.json"
        report_path = staging_dir / "report.json"
        transactions_path.write_text(
            json.dumps(transactions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staging_dir.rename(run_dir)

    final_transactions = run_dir / "transactions.json"
    final_report = run_dir / "report.json"
    import_command = (
        "uv run python -m investment_ledger --format json import "
        f"{_powershell_quote(str(final_transactions))}"
    )
    return PrepareOutcome(
        run_dir=run_dir,
        transactions_path=final_transactions,
        report_path=final_report,
        counts=counts,
        import_command=import_command,
    )
