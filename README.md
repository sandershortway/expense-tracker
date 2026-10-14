# expense-tracker

A personal financial tracking application with a local stock/ETF transaction
ledger. The project uses `uv`, Ruff, pytest, and pre-commit for development.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) **0.13.0 or newer** (required for managed
  CPython 3.15; check with `uv --version`, upgrade with `uv self update`).

## Setup

From a fresh checkout:

```sh
uv sync
```

`uv` automatically downloads CPython 3.15 (per `.python-version`), creates
`.venv`, and installs the locked dev dependencies — no manual virtual
environment or activation needed.

Install the pre-commit hooks:

```sh
uv run pre-commit install
```

## Commands

| Task             | Command                    |
| ---------------- | -------------------------- |
| Sync environment | `uv sync`                  |
| Format code      | `uv run ruff format .`     |
| Lint             | `uv run ruff check .`      |
| Run tests        | `uv run pytest`            |
| Install hooks    | `uv run pre-commit install`|

## Investment transaction ledger

The local SQLite ledger stores executed stock and ETF buy/sell transactions.
The `holdings` command aggregates them into per-instrument positions; it does
not fetch market prices or compute current market value.

Use the CLI from the repository root:

```powershell
uv run python -m investment_ledger --db .data/investments.sqlite3 list
uv run python -m investment_ledger add
uv run python -m investment_ledger import trades.json
Get-Content -Raw trades.json | uv run python -m investment_ledger --format json import -
```

`add` prompts for one transaction. JSON import expects an array of transaction
objects; decimal fields must be strings. `--format json` emits machine-readable
results. A duplicate import candidate requires a terminal confirmation. The
default database is `.data/investments.sqlite3` (ignored by Git); override it
with the global `--db PATH` option or `INVESTMENT_LEDGER_DB` environment
variable. CLI options precede the subcommand.

Each transaction requires `side`, `instrument_type`, `ticker`, `exchange`,
`trade_date` (`YYYY-MM-DD`), `quantity`, `unit_price_eur`, and
`gross_amount_eur`. Optional fields are `name`, `fee_eur`, and `currency`
(which must be `EUR` when supplied). Quantity supports up to 8 decimal places,
unit price up to 6, and EUR amounts up to 2. Gross amount is quantity times
unit price rounded half-up to cents; fees are separate.

Example JSON:

```json
[
  {
    "side": "buy",
    "instrument_type": "etf",
    "ticker": "VWCE",
    "exchange": "XETR",
    "trade_date": "2024-01-02",
    "quantity": "2.5",
    "unit_price_eur": "100.00",
    "gross_amount_eur": "250.00",
    "fee_eur": "1.00",
    "name": "Vanguard FTSE All-World"
  }
]
```

Other commands are `list`, `edit TRANSACTION_ID`, and
`delete TRANSACTION_ID --yes`. Use `--help` for options. Invalid JSON rows are
reported individually while valid rows are saved. The CLI returns a nonzero
status if any import row is rejected or skipped.

## Holdings and cost basis

```powershell
uv run python -m investment_ledger holdings
uv run python -m investment_ledger holdings --ticker NVDA
uv run python -m investment_ledger --format json holdings
```

`holdings` folds each instrument's transactions in trade-date order and
reports one position per ticker/exchange pair plus overall totals. It only
reads the ledger — the command never writes to the database.

Cost basis uses the **average-cost** convention: buys add `gross + fee` to the
position's cost, and sells release the proportional share of the remaining
cost basis while realizing `(gross - fee) - released` as profit/loss. Fully
closed positions stay listed with zero quantity so realized P&L remains
visible; selling more than held produces a warning rather than an error.

Each position reports `net_quantity`, `cost_basis_eur`, `average_cost_eur`,
`total_invested_eur`, `total_proceeds_eur`, `realized_pnl_eur`,
`total_fees_eur`, `transaction_count`, `first_trade_date`,
`last_trade_date`, and any warnings. `--format json` emits the same fields
with decimal values as strings under `holdings` plus a `totals` object.

## Pre-commit behavior

Each commit runs, in order:

1. **ruff format** — reformats staged Python files. If formatting changes a
   file, the commit is blocked until the changes are re-staged.
2. **ruff check** — lints staged Python files.
3. **pytest** — runs the full test suite on every commit. If the suite is empty,
   pytest's “no tests collected” exit code is treated as passing.

Hooks invoke `uv run`, so they use the same locked tool versions as manual
commands.
