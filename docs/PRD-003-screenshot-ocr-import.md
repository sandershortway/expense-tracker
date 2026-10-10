# PRD-003: Prepare Investment Purchase Screenshots for Ledger Import

**Priority:** Next import milestone after PRD-002; prepares the user's existing
screenshots for ledger entry.
**Area:** Local screenshot OCR, transaction extraction, import preparation, and
safe source-file organization.
**Dependencies:** PRD-002.
**Status note:** Verified on `main` at `57bbe32`: PRD-002 provides
`uv run python -m investment_ledger ... import`, which accepts a JSON array of
validated transactions. The user-provided `data/screenshots/` folder currently
contains seven PNGs: four share-purchase screenshots and three dividend
receipts. These source images are untracked personal files and must not be
committed.

## Problem

The user has Dutch-language stock/ETF purchase screenshots that need to become
ledger transactions. Manually transcribing amounts, prices, dates, and product
identity is error-prone. The current import CLI already validates its JSON
contract, but the screenshots show quantities rounded to two decimal places;
using those displayed quantities directly can fail the ledger's exact
`quantity * unit_price_eur = gross_amount_eur` validation. The import workflow
must therefore produce a reviewable, CLI-compatible JSON draft while preserving
unreadable or unsupported source images for later handling.

## User story

As an investor with screenshots of executed stock/ETF purchases, I want a local
utility to recognize the supported Dutch transaction screens and prepare a
reviewable JSON import, so that I can verify OCR results before saving them in
the investment ledger.

## Requirements

1. The existing investment CLI must provide a `prepare-screenshot-import`
   command. It must prepare data only; it must not write to the investment
   database or automatically invoke the existing `import` command.

2. The command must scan supported image files in the top level of
   `data/screenshots/` by default, with an input-directory override for tests
   and other local batches. It must not recursively scan the `done/` directory
   or files already named with the `dividend_` prefix. PRD-003 initially
   supports PNG files using the Dutch-language transaction-screen layout
   represented by the supplied screenshots; other layouts and languages are
   out of scope.

3. OCR must run locally using a Python OCR package and CPU inference. Screenshots
   and OCR text must not be sent to a cloud service. The OCR package and model
   setup must use the repository's `uv` workflow and be compatible with the
   project's Python 3.15 requirement. The OCR dependency must not change the
   behavior of the existing ledger commands.

4. The parser must recognize Dutch share-purchase screens (headed
   `Aankoop aandeel`) and extract the displayed product name, localized trade
   date, headline EUR amount, displayed quantity, per-share purchase price, and
   fee when shown. It must parse Dutch month names and European EUR number
   formatting (period thousands separator and comma decimal separator). The
   current ledger stores trade date only, so the timestamp's date is imported
   and the time is retained only in the review report.

5. Only recognized share-purchase screenshots may produce import rows in this
   release. Dividend receipts (headed `Ontvangen dividend`) are recognized as
   unsupported, excluded from the import JSON, and included in the review
   report. Other event types or unrecognized layouts must not be guessed into a
   buy or sell transaction.

6. The screenshot's displayed share quantity is informational and may be
   rounded to two decimal places. The utility must derive the import quantity
   from `gross_amount_eur / unit_price_eur` using `Decimal`, rounded half-up to
   at most 8 decimal places. The derived quantity must both:
   - pass the PRD-002 transaction validation that rounds
     `quantity * unit_price_eur` to the captured gross amount; and
   - round to the screenshot's displayed two-decimal quantity.

   If either check fails, the screenshot must be classified as needing review
   and must not produce an import row. The screenshot's displayed quantity and
   derived quantity must both be recorded in the report so the adjustment is
   auditable. The fee is separate from gross amount and must not be added to or
   subtracted from it.

7. The instrument label is not sufficient to infer a ticker, exchange, or asset
   type. For each distinct product label in one command invocation, the utility
   must request a session-only mapping to the required `instrument_type`
   (`stock` or `etf`), ticker, and exchange. It must reuse that answer for
   subsequent screenshots with the same label during that invocation, but must
   not persist the mapping. If the user declines, supplies invalid fields, or
   the command cannot prompt, affected screenshots must be reported as needing
   review and must not produce import rows.

8. Processing must fail closed. Only screenshots with a confidently recognized
   event type, complete required values, successful instrument mapping, and a
   quantity that passes PRD-002 validation may appear in the import-ready JSON.
   Incomplete, ambiguous, or low-confidence records must be omitted from that
   JSON and receive a per-image status and actionable reason in the review
   report. The implementation must select and document an OCR-confidence rule
   appropriate to the chosen backend before release.

9. The command must create a unique run directory under
   `.data/screenshot-import/` containing:
   - `transactions.json`: a top-level JSON array containing only PRD-002 import
     fields, with decimal fields encoded as strings and no OCR metadata; and
   - `report.json`: one result per processed screenshot, including source name,
     classification/status, extracted values, displayed and derived quantity
     where applicable, OCR confidence/warnings, and any failure reason.

   The command must print a copy-ready Windows PowerShell command using the
   existing `uv run python -m investment_ledger --format json import` entry
   point and a correctly quoted actual `transactions.json` path. It must not
   overwrite a prior run directory or artifact. `.data/` is already Git-ignored.

10. Purchase screenshots that produced valid JSON rows must be moved to
    `data/screenshots/done/` only after both output files have been written
    successfully. Source files must never be deleted or overwritten. A move
    collision must use a unique destination name; a failed move must leave the
    source in place and be recorded in the report. A failure writing either
    artifact must leave all source images unmoved and unrenamed.

11. A successfully classified dividend receipt must stay in the screenshot
    folder and be renamed to
    `dividend_<instrument-slug>_<sequence>.png`. The sequence is a three-digit,
    per-instrument counter starting at `001` and must advance to avoid existing
    names. Prefixing it `dividend_` prevents the command from OCRing it again.
    If the instrument name cannot be identified confidently, leave the source
    filename unchanged and report the issue.

12. A second invocation must skip the `done/` folder and `dividend_` files, so
    previously handled images are not reprocessed. Images needing review remain
    unchanged in the input folder for correction and a later run.

13. The review JSON must be manually inspectable and editable before it is
    passed to the existing CLI. Import remains a separate explicit user action;
    the utility must never create, edit, or delete ledger records.

## Acceptance criteria

- On a clean working copy of the supplied screenshots, the command recognizes
  four purchase screens and three dividend receipts. The import-ready JSON
  contains only the four valid purchases; each dividend is reported and
  renamed but excluded from the JSON.
- Each purchase JSON record contains exactly the PRD-002 import fields and can
  be loaded by the existing transaction validator. Decimal values are strings,
  dates are `YYYY-MM-DD`, and the derived quantity satisfies the existing gross
  amount/unit-price invariant while rounding to the displayed quantity.
- The report preserves each source filename, extracted values, the displayed
  quantity, derived quantity, OCR status/confidence, and any warning. No
  metadata-only field appears in a transaction JSON object.
- For repeated product labels within one invocation, the identity prompt is
  shown once and the answer is applied consistently to those rows. Declining or
  canceling a mapping excludes those rows and leaves their source images in the
  input folder.
- Recognized dividends receive per-instrument sequence names such as
  `dividend_NVIDIA_001.png`; existing names are never overwritten, and a second
  invocation does not rename or process them again.
- Valid purchase source images move to `done/` only after the JSON and report
  have been written. A simulated output-write failure leaves all input images
  unchanged; a simulated move failure leaves that source in place and is
  reported.
- Low-confidence or inconsistent OCR fields, unknown transaction types, and
  unsupported image layouts produce no import row and leave the source image
  unchanged, with an actionable report entry.
- The utility creates its run artifacts under `.data/screenshot-import/`,
  refuses collisions rather than overwriting prior review data, prints the
  correct existing CLI import command, and never changes the investment
  database by itself.
- A second run over the same input directory processes no already-handled
  purchases or renamed dividends. Screenshots are not added to the Git history.

## Out of scope

- Importing dividend receipts or adding dividend records to the ledger; they
  are only classified, renamed, and reported for a later PRD.
- Sell transactions, pending orders, arbitrary brokerage templates, other
  languages, PDF/CSV statements, or non-EUR transactions.
- Cloud OCR, cloud storage, market/security lookup, ticker discovery, or
  persistent instrument mappings.
- Automatic import into the SQLite database, portfolio calculations, live
  pricing, or financial advice.
- GPU OCR. This release uses local CPU inference for the small screenshot batch.
- Committing user screenshots, OCR run artifacts, or generated financial data.

## Implementation plan: individual commits

1. **`Add a local CPU OCR backend`** — Select a Python OCR package that works
   with the repository's Python 3.15 and `uv` constraints, add it through `uv`,
   and provide a local OCR adapter with no cloud dependency. Addresses
   requirements 2 and 3. Scope: OCR engine setup and adapter boundary; no
   transaction parsing or file moves. Tests: adapter output normalization,
   image-open/OCR errors, and a deterministic smoke test using a generated or
   sanitized image. Verify: `uv sync --locked`, `uv run pytest`, and
   `uv run ruff check .`.

2. **`Parse and validate Dutch purchase screenshots`** — Parse event labels,
   Dutch dates, European EUR amounts, fees, displayed quantities, and product
   names; prompt for session-only instrument mapping; derive exact quantities
   and validate rows with the existing transaction model. Addresses
   requirements 4-8. Scope: OCR text-to-candidate transformation only. Tests:
   localized number/date parsing, all required fields, fees kept separate,
   quantity derivation/reconciliation, mapping reuse/cancellation, unsupported
   dividends, and low-confidence rejection. Verify: `uv run pytest`.

3. **`Prepare reviewable CLI-compatible JSON`** — Add the
   `prepare-screenshot-import` CLI command, run directory, transaction array,
   per-image report, non-overwrite behavior, and printed import invocation.
   Addresses requirements 1, 9, and 13. Scope: file outputs only; must not
   mutate SQLite. Tests: exact import schema/Decimal strings, parseable JSON,
   unique run directories, output collisions, report completeness, and proof
   that the ledger remains unchanged. Verify: `uv run pytest`.

4. **`Safely organize processed screenshots`** — Move valid purchase screenshots
   into `done/`, rename classified dividends with per-instrument sequence
   numbers, preserve failed/uncertain inputs, and make reruns skip completed
   files. Addresses requirements 5, 10-12. Scope: file disposition after
   successful output generation. Tests: move/rename success, collision handling,
   output failure before mutation, partial move failure, unsupported/uncertain
   file retention, and rerun idempotence using temporary directories. Verify:
   `uv run pytest`.

5. **`Document the screenshot preparation workflow`** — Document the command,
   local OCR setup, session-only mappings, output/review process, and explicit
   follow-up invocation of the existing JSON import. Addresses requirements 3,
   7, 9, and 13. Scope: README/setup documentation only. Tests: documentation
   examples match CLI help and are covered by CLI tests. Verify: `uv run pytest`,
   `uv run ruff check .`, and `uv run ruff format --check .`.

## Verification notes

- Use temporary source/output directories in automated tests; do not move,
  rename, or alter the user's actual screenshot files during unit tests.
- Do not add the supplied screenshots to Git. Use generated/sanitized screenshot
  fixtures or injected OCR text results in unit and integration tests.
- Include an opt-in manual acceptance check using a disposable copy of the
  seven supplied PNGs. Verify there are four purchase candidates, three
  dividend exclusions, valid CLI JSON, correct movement/renaming, and a
  second-run no-op before touching the originals.
- Test that OCR is local and CPU-only and that list/import commands continue to
  work independently of OCR model initialization.
- The numeric OCR confidence threshold and exact compatible OCR package must
  be selected and documented after evaluating the local Python 3.15-compatible
  backend; do not claim compatibility or OCR accuracy until verified.

## Open questions

- [x] Which local Python OCR package provides acceptable Dutch OCR accuracy on
  this screen format while installing under Python 3.15 through `uv`?
  **Resolved:** `pytesseract` (pure-Python wrapper) plus the local Tesseract 5
  binary with the `nld` traineddata file. `pytesseract` and `pillow` install
  cleanly under Python 3.15 via `uv`; inference is local and CPU-only.
- [x] What confidence threshold should gate import readiness for the selected
  backend? **Resolved:** Tesseract reports word confidence 0-100. Every
  template token used for a required value must score at least 45; the
  superscript cents pass must return exactly two digits via a digit whitelist;
  and the derived-quantity reconciliation (requirement 6) remains the
  authoritative check before a row may be imported.
