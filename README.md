# expense-tracker — personal financial dashboard

A personal financial dashboard that runs locally on your own machine. The
backend is a FastAPI application, and a web frontend will call its API.
Planned modules:

- **Investments** — stock and ETF portfolio tracking (in progress)
- **Expenses** — expense tracking (planned)
- **Crypto** — crypto portfolio tracking (optional, later)

The project uses `uv`, FastAPI, Ruff, mypy, pytest, and pre-commit.

## Repository layout

```text
backend/                  Python backend (uv workspace member "findash")
  pyproject.toml          backend package metadata and runtime dependencies
  src/findash/
    main.py               FastAPI app factory (create_app)
    __main__.py           `findash` start command
    core/
      settings.py         configuration from FINDASH_* environment variables
      database.py         engine, sessions, transactions, UTC timestamps
      errors.py           application errors and the JSON error format
    investments/          stock/ETF module
      api.py              HTTP endpoints (translate HTTP <-> service)
      schemas.py          request/response shapes and input validation
      service.py          business operations; commits successful writes
      repository.py       data access: create and read rows
      models.py           database tables (SQLAlchemy models)
      errors.py           this module's errors (not found, conflicts)
      isin.py             ISIN format and check-digit validation
      dependencies.py     per-request database session
      database.py         applies this module's migrations
      migrations/         Alembic migrations for the investments database
  tests/                  backend tests (core/, investments/, app)
docs/                     PRDs for current work
docs/archive/             PRDs of the earlier CLI-based ledger
alembic.ini               Alembic configuration, one section per module
pyproject.toml            uv workspace root and tool configuration
uv.lock                   single lockfile for the whole workspace
```

Code is grouped by feature: each module (such as `investments`) holds its own
database, service, and API code, while `core` holds what modules share. A
`frontend/` directory will be added once UI work starts.

Within a module, a request flows through layers that each have one job:

```text
api.py  ->  service.py  ->  repository.py  ->  models.py / database
(HTTP)      (business rules,  (queries, never     (tables and
             commits)          commits)            constraints)
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) **0.13.0 or newer** (required for managed
  CPython 3.15; check with `uv --version`, upgrade with `uv self update`).

## Setup

From a fresh checkout, in the repository root:

```sh
uv sync
uv run pre-commit install
```

`uv` downloads CPython 3.15 (per `.python-version`), creates `.venv`, and
installs the backend package plus the locked development tools. There's no
need to create or activate a virtual environment manually. Run every command
below from the repository root.

## Running the API

```sh
uv run findash
```

The server starts at <http://127.0.0.1:8000> and is only reachable from your
own machine. Use `--host` and `--port` to change this, and stop it with
Ctrl+C.

- <http://127.0.0.1:8000/docs> — interactive API documentation, where you can
  try every endpoint
- <http://127.0.0.1:8000/api/health> — health check, returns
  `{"status": "ok"}`

## Investments API

In `/docs`, open an endpoint, click **Try it out**, fill in the request, and
click **Execute**.

### Instruments

| Method and path                            | Purpose                       |
| ------------------------------------------ | ----------------------------- |
| `POST /api/investments/instruments`        | create an instrument          |
| `GET /api/investments/instruments`         | list all instruments (by ID)  |
| `GET /api/investments/instruments/{id}`    | get one instrument            |

Create request:

```json
{
  "isin": "US67066G1040",
  "ticker": "NVDA",
  "name": "Nvidia",
  "legal_name": "NVIDIA Corporation"
}
```

`isin`, `ticker`, and `name` are required; `legal_name` is optional. The ISIN
must have a valid format and check digit. ISIN and ticker are converted to
uppercase and surrounding whitespace is removed. A successful create returns
`201 Created` with a `Location` header and the stored instrument:

```json
{
  "id": 1,
  "isin": "US67066G1040",
  "ticker": "NVDA",
  "name": "Nvidia",
  "legal_name": "NVIDIA Corporation",
  "created_at": "2026-10-14T19:30:00Z",
  "updated_at": "2026-10-14T19:30:00Z"
}
```

Instruments can't be edited or deleted yet.

### Errors

Invalid input returns `422` with FastAPI's standard `detail` list, which
names each invalid field. Business errors use one JSON shape:

```json
{"error": {"code": "instrument_exists", "message": "an instrument with ISIN US67066G1040 already exists"}}
```

| Status | Code                   | When                                  |
| ------ | ---------------------- | ------------------------------------- |
| 404    | `instrument_not_found` | no instrument with that ID            |
| 409    | `instrument_exists`    | an instrument with that ISIN exists   |

## Database

Each module has its own SQLite database. The investments database lives at
`.data/investments.db` by default (`.data/` is Git-ignored). To use another
location or database, set a SQLAlchemy URL:

```powershell
$env:FINDASH_INVESTMENTS_DATABASE_URL = "sqlite:///C:/path/to/investments.db"
```

`uv run findash` applies any pending migrations before the server starts, so
the database is created and kept up to date automatically.

### Schema changes

The schema is managed by [Alembic](https://alembic.sqlalchemy.org/)
migrations, which live in `backend/src/findash/investments/migrations/`.
Every change to a model in `models.py` must ship with a migration in the same
commit; a test fails when the models and migrations differ.

```sh
uv run alembic -n investments revision --autogenerate -m "add trades"
uv run alembic -n investments upgrade head
uv run alembic -n investments current
uv run alembic -n investments check
```

Review each generated migration before committing it. `check` reports
whether the models contain changes that no migration covers yet.

## Development commands

| Task                 | Command                             |
| -------------------- | ----------------------------------- |
| Sync environment     | `uv sync`                           |
| Start the API        | `uv run findash`                    |
| Run tests            | `uv run pytest`                     |
| Type check           | `uv run mypy`                       |
| Lint                 | `uv run ruff check .`               |
| Format code          | `uv run ruff format .`              |
| Run all hooks        | `uv run pre-commit run --all-files` |
| Apply migrations     | `uv run alembic -n investments upgrade head` |

## Pre-commit behavior

Each commit runs, in order:

1. **ruff format** — reformats staged Python files. If formatting changes a
   file, the commit is blocked until the changes are re-staged.
2. **ruff check** — lints staged Python files.
3. **mypy** — type checks `backend/src` and `backend/tests` in strict mode.
4. **pytest** — runs the full test suite.

Hooks invoke `uv run`, so they use the same locked tool versions as manual
commands.

## Roadmap

1. Backend foundation: this layout, the API shell, and type checking (done)
2. Database setup: settings, SQLAlchemy, Alembic migrations, `instruments`
   table and repository (done)
3. Instruments API: create, list, and get instruments (done)
4. Trades
5. Dividends
6. Holdings and average cost basis

Personal financial data (databases under `.data/`, source files under
`data/`) stays local and is never committed.
