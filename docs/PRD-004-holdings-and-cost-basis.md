# PRD-004: Holdings and Cost Basis from the Transaction Ledger

**Priority:** Next analytics milestone after PRD-002/003; turns the stored
ledger into the first meaningful dashboard number.
**Area:** Investment ledger domain logic and CLI output.
**Dependencies:** PRD-002 (transaction schema and storage). PRD-003 supplies
the data but is not required.
**Status note:** Verified on `main` at `3dec176`: the ledger stores validated
buy/sell rows in `.data/investments.sqlite3` and `list` returns them in
insertion order with `entry_order`, `trade_date`, `side`, `quantity`,
`unit_price_eur`, `gross_amount_eur`, `fee_eur`, `ticker`, `exchange`,
`instrument_type`, and `name`. No sell transactions exist in the user's data
yet; the OCR importer currently produces buys only.

## Problem

The ledger faithfully records executed trades but answers no questions. The
user cannot see what they currently own, what it cost them, or whether a sale
made or lost money — the calculations that every later dashboard view needs.
Deriving positions by hand from `list` output is error-prone, and the choice
of cost-basis convention changes the numbers, so it must be defined and
tested centrally rather than reimplemented in a UI later.

## User story

As an investor reviewing my portfolio, I want the CLI to aggregate my stored
transactions into per-instrument positions with net quantity, cost basis,
average purchase price, and realized profit/loss, so that I can see what I
own and what it cost before market-value and dashboard features arrive.

## Requirements

1. The existing CLI must provide a `holdings` command that reads the stored
   transactions and prints the computed positions. It must never write to
   the database and must work with the global `--db` and `--format`
   options like the other commands.

2. Positions must be grouped by the `(ticker, exchange)` identity pair.
   Each position carries the `instrument_type` and the most recent `name`
   seen for that identity.

3. Each position must be computed by folding its transactions in
   chronological order (`trade_date`, then `entry_order` as the tiebreaker,
   since imports may arrive out of order):
   - A `buy` adds `quantity` to the net position and adds
     `gross_amount_eur + fee_eur` to the cost basis (fees are capitalized
     into the purchase cost).
   - A `sell` removes `quantity` from the net position, releases the
     proportional share of the remaining cost basis
     (`cost_basis * sold / held_before`), and adds
     `(gross_amount_eur - fee_eur) - released_cost` to realized
     profit/loss.

   This is the average-cost (GAK) convention. All arithmetic uses
   `Decimal`; stored quantities keep their precision and reported EUR
   values round half-up to cents, consistent with PRD-002.

4. Each holding must report: `ticker`, `exchange`, `instrument_type`,
   `name`, `net_quantity`, `cost_basis_eur`, `average_cost_eur`
   (cost basis divided by net quantity while the position is open),
   `total_invested_eur` (sum of buy gross + fees), `total_proceeds_eur`
   (sum of sell gross - fees), `realized_pnl_eur`, `total_fees_eur`,
   `transaction_count`, `first_trade_date`, `last_trade_date`, and a
   `warnings` list.

5. Selling more than the held quantity is a data anomaly, not a crash: the
   command must clamp the released cost to the available cost basis, record
   a warning on that holding naming the oversold amount, and continue with
   a possibly negative net quantity.

6. A fully closed position (net quantity reaches zero) must still appear
   with `net_quantity` zero and empty `average_cost_eur`, so realized
   profit/loss remains visible.

7. The command must print a totals section summing cost basis, invested,
   proceeds, realized P&L, and fees across all holdings. Holdings are
   ordered by ticker, then exchange.

8. `--format json` must emit a machine-readable object
   (`{"count", "holdings": [...], "totals": {...}}`) with all decimal
   values encoded as strings, matching the existing CLI's conventions. The
   human-readable output must show the same fields legibly.

9. A `--ticker` option must restrict output to one position (matched
   case-insensitively); an unknown ticker yields an empty result, not an
   error.

10. An empty ledger must produce an empty holdings list and totals of zero
    with exit status 0.

## Acceptance criteria

- With a ledger containing only the four known purchases (NVIDIA buys of
  100.00, 480.00, and 1000.00 EUR plus fees 0.00, 4.75, and 9.90, and one
  2000.00 EUR ETF buy with a 19.80 fee), the command reports two holdings:
  NVIDIA with net quantity `10.96618209`, cost basis `1594.65`, and no
  realized P&L; and the ETF with net quantity `52.50721974` and cost basis
  `2019.80`. The totals row matches their sums.
- Selling half a position releases exactly half its remaining cost basis
  and realizes `(gross - fee) - released` as `realized_pnl_eur`; the
  remaining cost basis and average cost stay consistent.
- Selling an entire position leaves a zero-quantity holding with
  `average_cost_eur` empty and the full realized P&L visible.
- Selling more than held produces a warning naming the oversold amount and
  does not abort the command.
- JSON output is parseable, all monetary values are strings, and the
  existing `add`, `list`, `edit`, `delete`, `import`, and
  `prepare-screenshot-import` commands are unchanged.
- An empty ledger prints no holdings and zero totals with exit status 0.

## Out of scope

- Market value, unrealized P&L, and any price data source (live quotes,
  manual price entry, or valuation snapshots) — those need a later PRD.
- FIFO/LIFO/specific-lot cost basis; the average-cost method is the only
  convention in this release.
- Dividend income, which has no record type yet (PRD-003 only renames
  dividend screenshots).
- Per-lot or per-transaction drill-down views.
- The expenses side of the finances (a separate subsystem).
- Dashboard/UI presentation; this PRD only adds a CLI command.

## Implementation plan: individual commits

1. **`Compute holdings and average cost basis`** — Add a pure domain fold
   that groups stored transactions by `(ticker, exchange)`, walks them in
   `(trade_date, entry_order)` order, and produces position objects with
   the fields in requirement 4, average-cost sell handling, oversell
   warnings, and zero-quantity positions. Addresses requirements 2-7.
   Scope: domain logic only, no CLI. Tests: buy accumulation, fee
   capitalization, sell release and realized P&L, fully closed positions,
   oversell warnings, multi-instrument grouping, out-of-order imports,
   and empty input. Verify: `uv run pytest`.

2. **`Add the holdings CLI command`** — Wire `holdings` into the parser and
   dispatch with `--ticker` filtering and both output formats. Addresses
   requirements 1 and 8-10. Scope: presentation only, no new persistence.
   Tests: seeded-ledger text output containing every reported field, JSON
   schema and decimal-string encoding, ticker filter hit and miss, and an
   empty ledger. Verify: `uv run pytest`.

3. **`Document holdings output`** — Document the command, the average-cost
   convention, and the reported fields in the README. Addresses
   requirements 3 and 8. Scope: documentation only; CLI help examples are
   covered by CLI tests. Verify: `uv run pytest`,
   `uv run ruff check .`, `uv run ruff format --check .`.

## Verification notes

- Tests seed the ledger through the existing `Ledger.add`/`add_many` API in
  temporary databases; no user data is touched.
- Include a fixture mirroring the four known purchases so the acceptance
  numbers above are checked exactly.
- Verify the command never mutates the ledger (table contents unchanged
  after a `holdings` run).

## Open questions

- [x] Cost-basis convention: **resolved** as average cost (GAK), matching
  how Dutch brokers present positions. FIFO lot tracking is out of scope
  and can be revisited if realized-gains reporting per lot is ever needed.
- [x] Fee treatment: **resolved** — buy fees capitalize into cost basis;
  sell fees reduce proceeds.
