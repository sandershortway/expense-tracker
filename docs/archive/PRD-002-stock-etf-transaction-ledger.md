# PRD-002: Persist Executed Stock and ETF Transactions

**Priority:** First application milestone after the project foundation; this
creates the source-of-truth ledger required before portfolio reporting.
**Area:** Local investment persistence, transaction validation, and CLI data
management.
**Dependencies:** PRD-001.
**Status note:** At PRD authoring, the repository contained only the
`uv`/Ruff/pytest foundation; implementation now follows this specification.

## Problem

Investment history needs a durable local record before a broader financial
dashboard can be built. Transactions entered now must preserve the facts needed
to derive holdings and performance later, without prematurely implementing
those calculations or coupling the ledger to a market-data provider.

## User story

As an individual investor, I want to record, review, correct, and delete
executed stock and ETF buy/sell transactions in a local database, so that I have
an auditable transaction ledger that can later support portfolio calculations.

## Requirements

1. The application must store investment transactions in a local SQLite
   database. The default path must be `.data/investments.sqlite3`, and an
   explicit command-line or environment override must be supported. The data
   directory and database artifacts must be ignored by Git.

2. The schema must be versioned and initialized automatically on first use.
   Opening a database created by a newer schema version must fail with a clear
   error rather than attempting a downgrade. All batch writes must run in a
   database transaction so a writer failure cannot leave a partially-written
   accepted set.

3. Each record must represent one executed buy or sell transaction. The
   supported sides are `buy` and `sell`. The ledger must not model submitted,
   pending, canceled, partially-filled, or otherwise unexecuted orders.

4. Each transaction must store the instrument's ticker and exchange. Both are
   required, trimmed, case-insensitive values and must be persisted in a
   normalized uppercase form. Each transaction must also store an instrument
   type of `stock` or `etf` and may store a non-empty `name`.

5. Each transaction must store a calendar `trade_date` in `YYYY-MM-DD` format.
   The trade date is date-only; no intraday time or timezone is captured.
   Because records represent executed trades, a future trade date must be
   rejected.

6. Each transaction must store a positive `quantity`, a positive
   `unit_price_eur`, and a positive `gross_amount_eur`. Fractional quantities
   are supported. Quantity has at most 8 decimal places, unit price has at most
   6 decimal places, and EUR gross amount has at most 2 decimal places. Values
   must be parsed and persisted using exact decimal semantics, not binary
   floating point.

7. For both buys and sells, `gross_amount_eur` must equal
   `quantity * unit_price_eur`, rounded to the nearest cent using
   half-up rounding. The gross amount excludes fees.

8. Each transaction may store `fee_eur`, a separate non-negative EUR amount
   with at most 2 decimal places. An omitted fee is stored as `NULL`, preserving
   the distinction between an unknown/absent fee and an explicitly supplied
   zero fee.

9. This release supports EUR only. Persisted transactions use `EUR` as their
   currency. If a caller supplies a currency field, any value other than `EUR`
   must be rejected.

10. Each transaction must have a stable transaction ID and a monotonically
    increasing entry order that preserves the order in which transactions were
    entered. For transactions sharing the same trade date, sorting by trade
    date and then entry order must reproduce the original entry order. Each
    transaction must also store `created_at` and `updated_at` operational
    RFC 3339 timestamps in UTC, distinct from the user-entered trade date.

11. The CLI must provide commands to add, list, edit, and delete transactions.
    `add` must support an interactive prompted workflow for a single
    transaction. `list` must expose every persisted transaction field. `edit`
    and `delete` must address a transaction by its stable ID. `edit` must
    validate the complete resulting record and refresh `updated_at`; `delete`
    must require explicit confirmation unless an explicit non-interactive
    confirmation option is provided.

12. The CLI must support importing a JSON array of transaction objects from a
    file or standard input. Required JSON fields are `side`,
    `instrument_type`, `ticker`, `exchange`, `trade_date`, `quantity`,
    `unit_price_eur`, and `gross_amount_eur`; optional fields are `name`,
    `fee_eur`, and `currency`. Decimal fields must be JSON strings so precision
    is not lost before parsing.

13. JSON import must validate rows independently: valid non-duplicate rows are
    saved and invalid rows are reported without aborting other valid rows. Row
    results must identify the input index and either the created transaction ID
    or a machine-readable validation error. A nonzero exit code is required if
    any row is rejected or skipped.

14. Import must detect likely duplicates among database rows and within the
    same batch. A likely duplicate has the same normalized ticker, exchange,
    side, trade date, quantity, unit price, gross amount, and fee, even if the
    optional name differs. Interactive imports must prompt for each candidate
    and insert it only on confirmation. If duplicate candidates exist and the
    import cannot prompt, it must fail before writing any rows with a clear
    requirement to rerun in a terminal; unattended imports must neither insert
    nor silently skip those candidates.

15. All CLI commands must support human-readable output and explicit
    machine-readable JSON output. Machine-readable results must be written to
    standard output, while prompts, progress, and diagnostics must not corrupt
    JSON on standard output. Successful commands return exit code 0; input,
    validation, and duplicate-confirmation failures return a nonzero input
    error code; operational failures return a distinct nonzero error code.

16. This release stores source transaction facts only. It must not calculate,
    persist, or display portfolio holdings, cost basis, realized or unrealized
    profit/loss, current market value, or sale sufficiency checks.

## Acceptance criteria

- A user can initialize the default database, enter a valid buy transaction
  through the prompted CLI, list it, edit a field, and observe the updated
  record and refreshed `updated_at` after reopening the application.
- A user can enter a valid sell transaction and delete it by transaction ID
  after explicit confirmation; the record no longer appears in a subsequent
  list.
- Records preserve up to 8 decimal places of quantity and 6 decimal places of
  unit price exactly across save, list output, and database reopen.
- A transaction whose gross amount differs from half-up cent-rounded
  `quantity * unit_price_eur` is rejected and is not persisted.
- Invalid side, instrument type, malformed or future date, non-positive
  quantity or price, negative fee, unsupported currency, and duplicate-free
  malformed records are rejected with actionable errors and no database write.
- A JSON batch containing valid and invalid rows saves the valid
  non-duplicate rows, reports per-row statuses and errors, and returns a
  nonzero exit code.
- An interactive JSON import containing a likely duplicate prompts before
  inserting it; declining leaves the database unchanged for that row.
- A non-interactive JSON import containing a likely duplicate fails before any
  writes and instructs the caller to rerun with a terminal.
- Human-readable and explicit JSON output modes can both list the same stored
  transaction data; JSON output remains parseable even when prompts are used.
- The default database path exists under `.data/`, can be overridden, and is
  ignored by Git so personal financial data is not committed.

## Out of scope

- Portfolio holdings, cost basis, realized or unrealized profit/loss, market
  value, performance calculations, charts, and sale/short-position validation.
- Live/current price retrieval, symbol lookup, market-data providers, broker
  API integration, and automatic trade synchronization.
- Web UI, GUI, dashboard navigation, or integration with a broader financial
  dashboard beyond producing a durable local transaction ledger.
- Pending, submitted, canceled, or partially-filled order lifecycle tracking.
- Multiple portfolios, brokerage accounts, users, authentication, currencies,
  and FX conversion.
- Dividends, interest, splits, mergers, transfers, deposits, withdrawals, and
  other non-trade cash or corporate actions.
- CSV/PDF imports and natural-language or in-app LLM parsing. An external LLM
  may generate the documented JSON, but no LLM integration is part of this
  release.
- Backup, cloud sync, encryption, and multi-user concurrent access.

## Implementation plan: individual commits

1. **`Define the investment transaction contract`** — Introduce validation for
   sides, instrument fields, trade dates, exact decimal scales, gross-amount
   rounding, fees, and currency. Addresses requirements 3-9. Scope: pure
   domain/data-contract validation and serialization; no database or CLI.
   Tests: valid/invalid field boundaries, ticker/exchange normalization,
   half-up gross calculation, fractional precision, date validation, and
   decimal-string serialization. Verify: `uv run pytest`.

2. **`Add the SQLite transaction ledger`** — Create the versioned schema,
   default `.data/investments.sqlite3` path, path override, Git ignore rules,
   stable IDs/entry order, timestamps, and repository-level CRUD. Addresses
   requirements 1, 2, and 10. Scope: persistence only; no user-facing command
   behavior. Tests: schema initialization, persistence across reopen, CRUD,
   invalid constrained records, update timestamps, newer-schema refusal, and
   transactional rollback. Verify: `uv run pytest` and `uv run ruff check .`.

3. **`Add prompted transaction-management commands`** — Expose add, list,
   edit, and delete workflows over the repository, including prompted entry,
   ID-based edit/delete, delete confirmation, and text/JSON output modes.
   Addresses requirements 11 and 15. Scope: single-transaction CLI only; no
   batch import. Tests: prompted add, list output in both modes, successful and
   rejected edits, confirmed/canceled deletes, output separation, and exit
   codes. Verify: `uv run pytest`.

4. **`Add JSON batch import and duplicate safeguards`** — Accept a JSON array
   from file or standard input, validate rows independently, commit accepted
   rows, return per-row results, prompt for duplicates interactively, and fail
   closed for duplicates without a terminal. Addresses requirements 12-15.
   Scope: batch input contract and CLI result handling only. Tests: malformed
   JSON, invalid/valid mixed batches, within-batch and persisted duplicates,
   TTY confirmation, non-TTY duplicate failure, JSON parseability, and exit
   codes. Verify: `uv run pytest`.

5. **`Document the ledger and CLI contract`** — Document setup, the JSON
   transaction shape, precision rules, duplicate behavior, output modes, exit
   codes, and database location/override. Addresses requirements 1, 11-15.
   Scope: user-facing documentation only. Tests: documentation examples are
   covered by existing CLI/integration tests or adjusted if names differ.
   Verify: `uv run pytest`, `uv run ruff check .`, and
   `uv run ruff format --check .`.

## Verification notes

- End-to-end verification must use a temporary database path so tests never
  read or modify the user's real `.data/investments.sqlite3`.
- CLI verification must cover both interactive prompts and redirected
  standard input/output. Duplicate prompts require a pseudo-terminal or an
  injectable prompt abstraction; non-interactive duplicate behavior must be
  tested without a terminal.
- JSON output must be parsed by tests rather than compared only as formatted
  text. Diagnostics must not make machine-readable standard output invalid.
- Tests must verify decimal round trips and calculations using `Decimal`; they
  must not assert behavior through binary floats.
- A real Git status check must confirm that generated SQLite files and the
  `.data/` directory remain untracked.

## Open questions

- None.
