# PRD-005: Prepare Bunq Investment Orders for Ledger Import

**Priority:** Next investment-data milestone; makes the user's existing Bunq
order export usable by the local ledger and holdings command.
**Area:** Bunq JSON conversion, instrument mapping, import preparation, and CLI.
**Dependencies:** PRD-002 (transaction schema and JSON import), PRD-004
(holdings validation after import).
**Status note:** On `main` at `5a4a5ed`, the ledger's `import` command accepts a
JSON array with required `side`, `instrument_type`, `ticker`, `exchange`,
`trade_date`, `quantity`, `unit_price_eur`, and `gross_amount_eur` fields.
The supplied local `bunq_investment_orders.json` is a versioned object with an
`orders` array, not that transaction array. It contains 25 completed EUR
orders (24 buys, one sell), seven distinct asset/ISIN pairs, and no ticker,
exchange, or instrument-type fields. Its rounded displayed quantity multiplied
by unit price differs from the supplied `total` for 24 rows. The source notes
that `total` may not be net or gross and that timestamps have no timezone.
The source file and all generated financial data are private local data and
must not enter Git history.

## Problem

The Bunq export preserves order facts but does not match the ledger's import
schema. It wraps the records in export metadata, uses asset names and ISINs
instead of the ledger's ticker/exchange/type identity, records local timestamps
rather than date-only trade dates, and includes a `total` value that does not
reconcile with the displayed quantity and unit price. Passing it directly to
the existing `import` command fails validation. Manually transforming 25 rows
risks corrupting buys, the sell, fees, dates, and duplicate orders.

## User story

As an investor, I want to prepare the Bunq order export into a reviewable JSON
array accepted by the transaction ledger, so that I can map each ISIN once,
inspect the transformed trade facts, and explicitly import them into SQLite.

## Requirements

1. Add a `prepare-bunq-import` CLI command that accepts a Bunq export JSON file
   (default `bunq_investment_orders.json`, overridable by a positional path)
   and writes a unique run directory under `.data/bunq-import/`. Preparation
   must not create, update, or delete ledger records and must not modify the
   source file.

2. Validate the Bunq export envelope and supported schema version before
   processing. The initial supported version is exactly `"1.0"`. Require an
   `orders` array and validate each order independently.
   Only completed EUR orders with supported `buy` or `sell` sides may produce
   an import row. Invalid, unsupported, or incomplete rows must be excluded
   from the import JSON and listed with an actionable per-order status/reason
   in the report. A malformed envelope or unsupported export version must
   fail the command without writing partial artifacts.

3. For each distinct ISIN, prompt once per command invocation for
   `instrument_type` (`stock` or `etf`), ticker, and exchange; reuse that
   mapping for all orders with the ISIN during the run. Do not infer ticker,
   exchange, or asset type from the name or ISIN, and do not persist mappings.
   If a mapping is declined, invalid, or cannot be requested because there is
   no interactive terminal, exclude the affected orders and report the reason.

4. Convert each accepted order to exactly the PRD-002 import fields:
   `side`, `instrument_type`, `ticker`, `exchange`, `trade_date`, `quantity`,
   `unit_price_eur`, `gross_amount_eur`, `fee_eur`, `currency`, and `name`.
   Decimal fields must be JSON strings. Map Bunq's `name` field to ledger
   `name` when it is a non-empty string; fall back to `asset` for older export
   rows that do not contain `name`. Preserve both `asset` and Bunq `legal_name`
   in the report. Map `side` and `quantity` directly, `unit_price` to
   `unit_price_eur`, `fees` to `fee_eur`, and `currency` directly. The
   resulting row must pass the existing `TransactionData` validator.

5. Use the user's confirmed trade-amount rule: preserve Bunq's displayed
   `quantity` and `unit_price`; calculate `gross_amount_eur` as their product
   rounded half-up to cents. Store the Bunq `fees` value separately in
   `fee_eur`. Use `Decimal` arithmetic only. The Bunq `total` field must not
   determine quantity or gross amount. For review only, calculate
   `calculated_total_eur` as `gross_amount_eur + fee_eur` (zero if fees are
   absent) and `difference_eur` as `calculated_total_eur - Bunq total`; record
   the difference and a warning in the report when they differ. A discrepancy
   against Bunq `total` is not by itself a reason to omit a row, because the
   export does not define that field's net/gross
   semantics. No amount may be silently adjusted to force agreement with
   `total`.

6. Convert the date portion of `date_local` to the ledger's `YYYY-MM-DD`
   `trade_date`. Do not apply a timezone conversion or invent an offset.
   Preserve the original local timestamp and nullable timezone in the report
   for review. Preserve `entry_id`, `order_id`, `source_url`, `isin`, Bunq
   `total`, original displayed quantity, unit price, and fees in the report;
   these metadata fields must not be added to transaction JSON objects.

7. Write a unique run directory containing:
   - `transactions.json`: a top-level array containing only rows that pass
     validation and have a valid instrument mapping, formatted for the
     existing `uv run python -m investment_ledger --format json import` command;
   - `report.json`: source file/version, coverage summary, and one result per
     source order with its source `entry_id`, status, mapping, source values,
     converted values, total discrepancy/warnings, and any reason for
     exclusion.

   Never overwrite an existing run directory or prior review artifacts.
   Print a correctly quoted, copy-ready command to import the generated
   `transactions.json` using the existing CLI. Import must remain a separate,
   explicit action.

8. Do not deduplicate or collapse rows by matching financial fields. Distinct
   Bunq `entry_id` values are distinct source orders even when fields match.
   Preserve the source-order sequence in generated transaction JSON and
   report. Let the existing ledger import's duplicate checks and interactive
   confirmation govern collisions with database rows or within the batch; do
   not suppress or auto-confirm them.

9. The command must support human-readable output and `--format json` without
   mixing prompts or diagnostics into machine-readable standard output. It
   must not initialize OCR, require Tesseract, or add OCR dependencies.

10. Automated tests must use synthetic/sanitized JSON fixtures and temporary
    output directories. Never use or commit the supplied personal export as a
    test fixture.

## Acceptance criteria

- Given a sanitized envelope matching the supplied file's shape, the command
  recognizes the `orders` array, supports both buy and sell, and produces a
  transaction array accepted by `TransactionData.from_mapping` and the
  existing JSON import command.
- For each order, the imported quantity is the supplied displayed quantity;
  `gross_amount_eur` is half-up cent-rounded quantity times unit price; and
  fees remain separate. The report shows the supplied Bunq total and the
  calculated gross-plus-fee total and flags differences without silently
  changing imported trade values.
- Mapping is requested once per distinct ISIN and reused; an unanswered or
  invalid mapping excludes only that ISIN's rows, with reasons in the report.
- The date-only field is extracted without timezone conversion, while the
  report preserves the local timestamp, source identifiers, original values,
  and conversion results.
- Incomplete, unsupported, non-EUR, uncompleted, invalid-decimal, future-date,
  or otherwise invalid orders do not become import rows and are reported
  individually; one bad row does not block other valid orders.
- Two source orders with distinct `entry_id` values are both retained even
  when their transaction fields otherwise match. Existing import duplicate
  checks still require confirmation in a terminal and fail closed when a
  duplicate batch is imported without one.
- A second preparation run creates a new unique output directory and leaves
  both the source file and earlier run artifacts unchanged.
- The printed import command targets the actual generated file. Running that
  command against a temporary database imports all valid prepared rows, reports
  duplicates according to existing behavior, and leaves the user's default
  database untouched during preparation.
- The command works without Tesseract installed and the existing `add`,
  `list`, `holdings`, `edit`, `delete`, and `import` commands continue to work.
- The Bunq export, screenshots/data, databases, and generated import artifacts
  are absent from Git changes.

## Out of scope

- OCR, screenshot import, broker APIs, web scraping, automatic synchronization,
  or another broker's export format.
- Importing Bunq coverage metadata, dividends (the source says they were
  excluded), deposits, withdrawals, or non-trade events.
- Changing the transaction schema to store Bunq source IDs, ISIN, timezone, or
  original Bunq `total`; source provenance is retained in the local report and
  source export, not the ledger row.
- Guessing or discovering ticker, exchange, or instrument type from ISIN/name;
  market/security lookup and persistent mappings are not included.
- Adjusting fees, quantity, price, or gross amount to reconcile Bunq `total`;
  the explicitly selected quantity × unit-price rule is used.
- Holdings, cost-basis, market valuation, or other portfolio analytics (PRD-004
  already covers holdings separately).

## Implementation plan: individual commits

1. **`Parse and validate Bunq order exports`** — Add a pure conversion layer
   that validates the envelope/orders and converts dates, Decimal strings,
   gross amounts, fees, and source metadata using the confirmed field mapping.
   Addresses requirements 2, 4-6, and 8. Scope: parser and data candidates
   only; no filesystem writes, prompts, or database changes. Tests: supported
   envelope/version, buys and sells, half-up gross calculations, quantity
   precision, missing/invalid fields, unsupported statuses/currencies,
   timezone-free date extraction, totals discrepancy reporting, and distinct
   source entry IDs. Verify: `uv run pytest`.

2. **`Prepare reviewable Bunq import artifacts`** — Add the CLI command,
   session-only ISIN mapping prompts, unique run artifacts, per-order report,
   and printed import invocation; keep import a separate user action.
   Addresses requirements 1, 3, 7, and 9. Scope: local file preparation only.
   Tests: prompt reuse/cancellation/non-TTY, output schema, no overwrite,
   malformed-envelope no-partial-output, no DB creation or mutation,
   machine-readable output separation, and integration import of generated
   JSON into a temporary database using the existing command. Verify:
   `uv run pytest`.

3. **`Document the Bunq JSON import workflow`** — Document the supported export
   shape, field mapping/accounting rule, ISIN prompts, discrepancy report,
   review-first process, and explicit existing import command. Addresses
   requirements 1, 5, and 7. Scope: README only. Tests: CLI help and example
   workflow remain covered by CLI tests. Verify: `uv run pytest`,
   `uv run ruff check .`, and `uv run ruff format --check .`.

## Verification notes

- The real `bunq_investment_orders.json` is private user data. Do not read it
  from automated tests, stage it, or use it as a committed fixture. Manual
  acceptance may use a disposable copy and a temporary SQLite database only
  after the generated JSON and report are reviewed.
- Verify actual export counts (25 total, 24 buys, one sell, seven ISINs) in an
  opt-in manual acceptance run; these are current file observations, not a
  promise about future exports.
- Inspect the generated report's total discrepancies. Per the user's selected
  rule, these are review warnings; the import row's quantity, unit price,
  gross, and fee are not rewritten to match Bunq `total`.
- Confirm duplicate handling explicitly, especially where existing ledger
  entries overlap economically but differ because of the Bunq displayed
  quantity precision. Existing exact-field duplicate detection may not
  recognize a rounded-quantity version of a previously imported trade.

## Open questions

- [x] Amount mapping: **resolved by the user** — use displayed quantity and
  unit price; set gross to their product rounded half-up to cents; preserve
  fees separately; do not use Bunq `total` to determine transaction fields.
- [x] Mapping workflow: **resolved by the user** — prompt once per ISIN per
  preparation run and reuse that mapping for its orders; do not persist it.
- [x] Discrepancy handling: **resolved by the user's amount-mapping choice** —
  report differences between Bunq `total` and calculated gross plus fee as
  warnings; do not require a second acknowledgement or alter the chosen
  quantity × unit-price values.
