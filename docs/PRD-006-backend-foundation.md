# PRD-006: Restructure the Repository Around a FastAPI Backend

**Priority:** Step 1 of the financial-dashboard plan; every later step
(database, instruments, trades, dividends, holdings) builds on this layout.
**Area:** Repository structure, Python packaging, developer tooling, and the
API application shell.
**Dependencies:** PRD-001 (uv, Ruff, pytest, pre-commit foundation).
**Status note:** On `main` at `41d0fe8`, the repository is a single,
non-packaged Python project (`package = false`). Its only application code is
the `investment_ledger` package, which provides a CLI, a raw-`sqlite3` ledger,
holdings calculation, and a Bunq importer. It has 88 passing tests under
`tests/`, and PRD-001 to PRD-005 live under `docs/`. Before writing this PRD, a
throwaway prototype of the target layout was verified on Python 3.15.0:

- a uv workspace with a `backend/` member package;
- `uv sync`, `uv run pytest`, `uv run mypy` (strict) and `uv run findash`, all
  run from the repository root;
- `GET /api/health` returning `{"status":"ok"}`, and the `/docs` page loading.

## Problem

The goal is a personal financial dashboard: a web app whose backend exposes
an API over a database, with investments as the first module and expenses
(and possibly crypto) later. The current repository is organised around a
CLI tool for one module, so it has no place for a web API, a future frontend,
or more modules. It also still contains Bunq-specific import code that is no
longer wanted.

Adding a database layer or endpoints on top of this layout would mix old and
new structures. A clean foundation is needed first: a monorepo layout, an
installable backend package grouped by feature, a minimal running API, and
stricter tooling (type checking). Every later step then only adds code.

## User story

As the sole developer and user of my financial dashboard, I want the
repository restructured into a backend package with a running, tested API
shell, so that I can add the database, module features, and later a frontend
in small, understandable steps on a clean foundation.

## Requirements

1. **Monorepo layout.** The repository root holds shared configuration
   (workspace and tool settings, pre-commit, `.python-version`, `AGENTS.md`,
   `README.md`, `docs/`). All Python application code and its tests live
   under `backend/`:
   - `backend/pyproject.toml`;
   - `backend/src/findash/` for the application package;
   - `backend/tests/` for its tests.

   No `frontend/` directory is created in this step.

2. **uv workspace.** The root project (still named `expense-tracker`, not
   packaged) is a uv workspace whose single member is `backend`. The member
   is an installable package named `findash`, built with the `uv_build`
   backend. There is exactly one lockfile (`uv.lock`) at the root, and Python
   3.15 stays selected through the root `.python-version`. Every documented
   command runs from the repository root.

3. **Package skeleton, grouped by feature.** `findash` contains:
   - an application module exposing an app factory, `create_app()`, which
     returns a configured FastAPI application, plus a module-level `app`
     created by it;
   - a command entry point (requirement 5);
   - empty `findash.core` and `findash.investments` subpackages, each with a
     docstring stating its purpose: shared plumbing (settings, database) for
     `core`, and the stock/ETF module for `investments`.

   No business logic, database code, or settings are added yet.

4. **Health endpoint.** `GET /api/health` returns HTTP 200 with the JSON body
   `{"status": "ok"}`. FastAPI's interactive API documentation is available
   at `/docs` and the OpenAPI schema at `/openapi.json`.

5. **Start command.** `uv run findash` starts the API server with uvicorn,
   bound to `127.0.0.1` on port `8000` by default. `--host` and `--port`
   options override these. The command does not enable auto-reload and does
   not run database migrations (there is no database yet).

6. **Dependencies.** Each dependency is added with `uv add` and must use a
   release published at least 7 days before it is added. As of 2026-10-14
   that means:
   - FastAPI 0.143.1 was published 2026-10-14, so it is constrained to
     `>=0.142.4,<0.143`;
   - uvicorn 0.54.0 (2026-09-25), mypy 2.4.0 (2026-10-01) and httpx2 2.13.1
     (2026-09-23) are eligible.

   Runtime dependencies of `findash` are `fastapi` and `uvicorn`. Development
   dependencies stay in the root dev group: pytest, Ruff, pre-commit, mypy,
   and `httpx2`, which FastAPI's `TestClient` needs. `httpx` is not used,
   because Starlette's test client emits a deprecation warning recommending
   `httpx2`.

7. **Tooling from the root.** These must all succeed from the repository root
   on the restructured code:
   - Ruff: the existing settings (79-character lines, rules
     `B, E, F, I, UP, W`) apply to `backend/`;
   - pytest: discovers `backend/tests` without extra arguments;
   - mypy: runs in strict mode over `backend/src` and `backend/tests`;
   - pre-commit: runs Ruff format, Ruff check, mypy, and pytest, in that
     order.

   A type error or failing test blocks a commit.

8. **Remove legacy code.** The `investment_ledger` package (CLI, raw-`sqlite3`
   ledger, Bunq conversion and preparation, holdings) and all of its tests
   are deleted, along with the root `tests/` directory. No compatibility shim
   is kept, and `uv run python -m investment_ledger` no longer works. The
   code remains in Git history at `41d0fe8`; the average-cost holdings logic
   and its tests will be ported from there in step 6.

9. **Archive old PRDs.** PRD-001 to PRD-005 move to `docs/archive/` with
   `git mv`, so their history is preserved and their content is unchanged.
   PRD-006 and later PRDs live directly in `docs/`.

10. **Documentation.** `README.md` describes:
    - the dashboard's purpose and planned modules;
    - the repository layout;
    - setup, the development commands (including mypy), and how to start the
      app and open `/docs`;
    - that the database and investment features arrive in upcoming steps.

    All sections about the old CLI, the Bunq import, and CLI holdings are
    removed. `AGENTS.md` is updated in the same way:
    - the new layout and the `uv run findash` command;
    - mypy added to the required checks;
    - the `investment_ledger` command line removed;
    - the existing branch, commit, pull-request, and local-financial-data
      rules kept.

11. **Local data untouched.** Nothing under `.data/` or `data/` is modified,
    moved, deleted, or committed. The old `.data/investments.sqlite3` stays on
    disk unused. Step 2 uses a new file name, so the two cannot clash.

## Acceptance criteria

- On a fresh clone of the branch, these all succeed from the repository root
  without manually creating or activating a virtual environment:
  - `uv sync --locked`;
  - `uv run pytest`;
  - `uv run ruff check .`;
  - `uv run ruff format --check .`;
  - `uv run mypy`;
  - `uv run pre-commit run --all-files`.
- `uv run findash` starts a server on `http://127.0.0.1:8000`. There,
  `GET /api/health` returns 200 with `{"status":"ok"}`, and `/docs` returns
  200. `uv run findash --port 8765` serves on port 8765 instead.
- Automated tests prove the health response, the availability of the OpenAPI
  schema, and that the start command passes the default host `127.0.0.1` and
  port `8000` (and the overrides) to uvicorn, without starting a real server.
- A deliberate type error in `backend/src` makes `uv run mypy` and the
  pre-commit hook fail.
- `investment_ledger/` and the root `tests/` directory no longer exist, and
  `git grep investment_ledger` finds matches only in PRD documents under
  `docs/`.
- PRD-001 to PRD-005 exist under `docs/archive/` with unchanged content, and
  Git reports them as renames.
- `uv.lock` contains `findash` as a workspace member. Its `fastapi` version is
  `<0.143`, and there is no `httpx` (only `httpx2`), no `pillow`, and no
  `pytesseract`.
- `README.md` and `AGENTS.md` contain no instructions for the removed CLI or
  the Bunq import, and document every command listed above.
- `git status` shows no changes under `.data/` or `data/`, and none of those
  files appear in any commit.

## Out of scope

- Database code of any kind: SQLAlchemy, Alembic, settings or environment
  variables, database URLs, and the investments database (step 2).
- Instruments, trades, dividends, holdings, their services and endpoints, and
  the structured error format (steps 3-6).
- Porting the average-cost holdings logic (step 6).
- Any frontend, CORS configuration, static file serving, or `frontend/`
  directory.
- Expenses or crypto modules beyond the empty placeholder package structure.
- Authentication, deployment, Docker, CI workflows, auto-reload or dev-mode
  options, logging configuration, and versioned (`/api/v1`) URLs.
- Renaming the GitHub repository or the root project.

## Implementation plan: individual commits

1. **`refactor: remove the legacy investment_ledger package`**
   - **Purpose:** delete the `investment_ledger` package, its tests, and the
     root `tests/` directory, starting from a clean slate. Addresses
     requirement 8.
   - **Scope:** deletions only. The root pytest configuration stays as it is
     until commit 3. With no tests left, pytest exits with "no tests
     collected" (exit code 5), which the pre-commit hook accepts; this was
     verified with a missing `testpaths` directory on Python 3.15.
   - **Tests:** none remain; the existing behaviour is intentionally removed.
   - **Verify:** `uv run ruff check .`, `uv run pre-commit run --all-files`,
     and `git grep investment_ledger -- ':!docs'` (expect no output).

2. **`docs: archive PRD-001 to PRD-005`**
   - **Purpose:** move the old PRDs to `docs/archive/` with `git mv`.
     Addresses requirement 9.
   - **Scope:** file moves only; no content edits.
   - **Tests:** none.
   - **Verify:** `git show --stat --find-renames HEAD` lists five renames.

3. **`build: set up the uv workspace and findash backend package`**
   - **Purpose:**
     - turn the root project into a uv workspace;
     - add `backend/pyproject.toml` (the `findash` package built with
       `uv_build`, runtime dependencies `fastapi>=0.142.4,<0.143` and
       `uvicorn`);
     - create the `backend/src/findash` skeleton with documented `core` and
       `investments` subpackages;
     - add `httpx2` to the dev group;
     - point pytest at `backend/tests`;
     - regenerate `uv.lock`.

     Addresses requirements 1-3, 6, and the Ruff and pytest parts of 7.
   - **Scope:** packaging and an empty skeleton; no endpoints yet.
   - **Tests:** a smoke test that imports `findash`, `findash.core`, and
     `findash.investments`.
   - **Verify:** `uv sync --locked`, `uv run pytest`, and
     `uv run ruff check .`.

4. **`feat(api): add the FastAPI app with a health endpoint and start command`**
   - **Purpose:**
     - add `create_app()` with `GET /api/health`;
     - add the `findash` script entry point, which runs uvicorn on
       `127.0.0.1:8000` with `--host` and `--port` overrides.

     Addresses requirements 4 and 5. Depends on commit 3.
   - **Scope:** application shell and entry point only.
   - **Tests** (using `TestClient`):
     - health returns 200 with the exact body;
     - `/openapi.json` is served and lists `/api/health`;
     - the entry point calls `uvicorn.run` with the default host and port,
       and with overridden values (with `uvicorn.run` monkeypatched).
   - **Verify:** `uv run pytest`, plus a manual `uv run findash` with requests
     to `/api/health` and `/docs`.

5. **`build: add strict mypy type checking`**
   - **Purpose:**
     - add mypy to the dev group;
     - configure strict mode over `backend/src` and `backend/tests` in the
       root `pyproject.toml`;
     - add a mypy hook to pre-commit between Ruff check and pytest;
     - make all existing code pass.

     Addresses requirement 7. Depends on commit 4.
   - **Scope:** tooling configuration and type annotations only.
   - **Tests:** the existing tests pass. Confirm manually that a deliberate
     type error fails both `uv run mypy` and the hook, then revert it.
   - **Verify:** `uv run mypy` and `uv run pre-commit run --all-files`.

6. **`docs: document the backend layout and workflow`**
   - **Purpose:**
     - rewrite `README.md` (purpose, modules, layout, setup, commands,
       running the app and `/docs`, upcoming steps);
     - update `AGENTS.md` (layout, `uv run findash`, mypy as a required check,
       the old CLI line removed, existing rules kept).

     Addresses requirement 10.
   - **Scope:** documentation only.
   - **Tests:** the documented commands are exactly the ones verified in
     commits 3-5.
   - **Verify:** `uv run pytest`, `uv run ruff check .`,
     `uv run ruff format --check .`, and `uv run mypy`.

## Verification notes

- After the last commit, repeat the full acceptance list on a fresh clone
  (or after deleting `.venv`) to prove that the lockfile and workspace
  configuration are complete. Then run `uv run findash` and request
  `/api/health` and `/docs` with real HTTP requests.
- The prototype showed that Starlette's `TestClient` warns when used with
  `httpx` and runs cleanly with `httpx2`. If the warning reappears with the
  locked versions, treat it as a failure to resolve rather than ignore.
- Re-check the 7-day release-age rule at implementation time. If newer
  eligible releases exist by then, prefer them and record the chosen
  versions in the PR description.
- Confirm with `git status` and `git diff --stat main...HEAD` that nothing
  under `.data/` or `data/` is touched.

## Open questions

- None. All structural decisions in this PRD (monorepo layout, `findash`
  package name, feature-based grouping, FastAPI, mypy, removing the legacy
  package and Bunq code, archiving old PRDs, keeping the repository name)
  were confirmed by the user during planning.
