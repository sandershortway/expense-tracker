# Repository Guidance

## Commits

Use Conventional Commit subjects in the form `<type>(<scope>): <imperative summary>`.
Choose a standard type such as `feat`, `fix`, `docs`, `test`, `refactor`, `build`, or `chore`; keep each commit focused and include its relevant tests. Examples:

- `feat(investments): persist executed transactions`
- `test(investments): cover exact decimal validation`
- `docs(investments): explain JSON import usage`

## Python Workflow

- Use `uv` to manage the Python environment and run Python commands.
- Run tests with `uv run pytest`.
- Run lint with `uv run ruff check .` and verify formatting with `uv run ruff format --check .`.
- The investment ledger CLI is available from the repository root with `uv run python -m investment_ledger`.

## Local Financial Data

- Keep the default investment database under `.data/`; this directory is Git-ignored.
- Do not add user-provided financial files, screenshots, or local database files to commits unless explicitly requested.
