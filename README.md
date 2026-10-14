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
    main.py               FastAPI app factory (create_app) and app
    __main__.py           `findash` start command
    core/                 shared plumbing: settings, database (upcoming)
    investments/          stock/ETF module (upcoming)
  tests/                  backend tests
docs/                     PRDs for current work
docs/archive/             PRDs of the earlier CLI-based ledger
pyproject.toml            uv workspace root and tool configuration
uv.lock                   single lockfile for the whole workspace
```

Code is grouped by feature: each module (such as `investments`) will hold its
own database, service, and API code, while `core` holds what modules share. A
`frontend/` directory will be added once UI work starts.

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
   table
3. Instruments API
4. Trades
5. Dividends
6. Holdings and average cost basis

Personal financial data (databases under `.data/`, source files under
`data/`) stays local and is never committed.
