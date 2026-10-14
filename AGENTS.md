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

## Repository Layout

- The repository root is a uv workspace (`pyproject.toml`, one `uv.lock`).
  The Python backend is the workspace member in `backend/`: the `findash`
  package lives in `backend/src/findash/` and its tests in `backend/tests/`.
- Group backend code by feature: each module (for example
  `findash.investments`) owns its own database, service, and API code;
  `findash.core` holds shared plumbing. A `frontend/` directory is added
  later.
- Write PRDs in `docs/`; PRDs for the retired CLI ledger are in
  `docs/archive/`.

## Python Workflow

- Use `uv` to manage the Python environment and run Python commands. Run all
  commands from the repository root.
- Add dependencies with `uv add` (`uv add --package findash ...` for backend
  runtime dependencies, `uv add --dev ...` for tooling).
- Start the API with `uv run findash` (http://127.0.0.1:8000, docs at
  `/docs`). It applies pending database migrations first.

## Database and Migrations

- Each module has its own database and its own SQLAlchemy declarative base.
  The investments database URL comes from
  `FINDASH_INVESTMENTS_DATABASE_URL` (default
  `sqlite:///.data/investments.db`).
- Every model change ships with an Alembic migration in the same commit:
  `uv run alembic -n investments revision --autogenerate -m "..."`, then
  review the generated file. The test suite fails when models and
  migrations differ.
- Repositories work on a session passed in by the caller and never commit;
  the caller owns the transaction.
- Tests use a fresh, migrated SQLite database in pytest's temporary
  directory; never point tests at `.data/`.
- Before committing, all of these must pass:
  - tests: `uv run pytest`
  - type check: `uv run mypy` (strict)
  - lint: `uv run ruff check .`
  - formatting: `uv run ruff format --check .`

## Local Financial Data

- Keep local databases under `.data/`; this directory is Git-ignored.
- Do not add user-provided financial files (such as those in `data/`),
  screenshots, or local database files to commits unless explicitly
  requested.
