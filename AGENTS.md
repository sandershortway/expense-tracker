# Repository Guidance

## Branches, Commits, and Pull Requests

- Create a dedicated branch for each PRD before making changes, named
  `<type>/prd-<ID>-<short-description>` (for example,
  `feat/prd-002-stock-etf-ledger`). Do not commit directly to or push to `main`.
- Break PRD work into focused, logical commits and include relevant tests with
  each behavior change.
- Use Conventional Commit subjects in the form
  `<type>(<scope>): <imperative summary>`. Choose a standard type such as
  `feat`, `fix`, `docs`, `test`, `refactor`, `build`, or `chore`. Examples:

  - `feat(investments): persist executed transactions`
  - `test(investments): cover exact decimal validation`
  - `docs(investments): explain JSON import usage`
- After the PRD work and verification are complete, push the branch and open a
  pull request targeting `main`.

## Python Workflow

- Use `uv` to manage the Python environment and run Python commands.
- Run tests with `uv run pytest`.
- Run lint with `uv run ruff check .` and verify formatting with `uv run ruff format --check .`.
- The investment ledger CLI is available from the repository root with `uv run python -m investment_ledger`.

## Local Financial Data

- Keep the default investment database under `.data/`; this directory is Git-ignored.
- Do not add user-provided financial files, screenshots, or local database files to commits unless explicitly requested.
