# PRD-007: Add the Investments Database and Instrument Repository

**Priority:** Step 2 of the financial-dashboard plan. Steps 3 to 6
(instruments API, trades, dividends, holdings) all read and write through the
database layer introduced here.
**Area:** Configuration, database plumbing, schema migrations, and the
investments data-access layer.
**Dependencies:** PRD-006 (backend foundation).
**Status note:** On `main` at `e1f846e`, `findash` is a FastAPI application
with only `GET /api/health`. It has empty `findash.core` and
`findash.investments` packages, no database dependency, no settings, and 8
passing tests. The planning decisions this PRD relies on were all confirmed
by the user:

- SQLite, kept easy to swap for another database;
- SQLAlchemy 2.0 in synchronous style, with Alembic migrations from day one;
- one database per module;
- the database location configured through
  `FINDASH_INVESTMENTS_DATABASE_URL`, defaulting to
  `sqlite:///.data/investments.db`;
- `uv run findash` applies pending migrations before it starts;
- tests run against fresh, real SQLite databases rather than mocks;
- integer IDs and `created_at`/`updated_at` on every row;
- instruments have `isin` (required, unique), `ticker` and `name` (required),
  and `legal_name` (optional);
- create and read only: no update or delete yet.

## Problem

The investments module needs durable storage before it can expose any
features. That storage needs four things:

- configuration that says where the database lives;
- a reusable way to open connections and transactions;
- a versioned, reviewable history of schema changes;
- a data-access layer that the service and API layers (step 3) call, instead
  of touching SQL directly.

Each of these must be testable on its own, and switching away from SQLite
later must mean changing configuration rather than rewriting code. Without
this layer, step 3 would have to invent database handling inside API code,
which mixes the layers the plan keeps separate.

## User story

As the developer of my financial dashboard, I want a configured, migrated
investments database with a tested repository for instruments, so that the
next steps can build services and API endpoints on top of a reliable,
swappable data layer.

## Requirements

1. **Dependencies.** Add the following with `uv add`, each using a release at
   least 7 days old:
   - backend runtime dependencies of `findash`: SQLAlchemy (2.1.4, published
     2026-10-07), Alembic (1.20.0, 2026-09-11), and pydantic-settings;
   - pydantic-settings is constrained to `<2.16`, because 2.16.0 was
     published 2026-10-14; this resolves to 2.15.0 (2026-08-07).

   Any newly added transitive release younger than 7 days is held back with
   `uv lock --exclude-newer-package`, as in PRD-006.

2. **Settings.** `findash.core.settings` defines a settings object built with
   pydantic-settings:
   - environment variable prefix `FINDASH_`;
   - one field, `investments_database_url`, defaulting to
     `sqlite:///.data/investments.db`. The relative path resolves against the
     current working directory, which is the repository root for every
     documented command.

   A function returns the settings. Tests can construct settings with
   explicit values without touching environment variables.

3. **Database helpers.** `findash.core.database` provides:
   - **creating an engine from a URL.** For file-based SQLite URLs, the
     parent directory of the database file is created if it doesn't exist.
     Every SQLite connection enables foreign-key enforcement
     (`PRAGMA foreign_keys=ON`), because steps 4 and 5 rely on foreign keys.
   - **a session factory.** Sessions don't expire objects on commit, so
     returned objects stay readable afterwards.
   - **a transaction context manager** that yields a session, commits on
     success, rolls back on any exception, and always closes the session.
   - **a reusable UTC timestamp column type.** It stores timezone-aware UTC
     datetimes and always returns timezone-aware UTC datetimes, even on
     SQLite, which has no native timezone support.

   Nothing in `core` imports from `investments`.

4. **One schema per module.** `findash.investments` has its own declarative
   base (its own metadata), separate from any future module. All of its
   tables belong to this base and live in the investments database only.

5. **`instruments` table.**

   | Column | Type | Rules |
   |---|---|---|
   | `id` | integer | primary key, auto-increment |
   | `isin` | string, up to 12 | NOT NULL, UNIQUE, exactly 12 characters, uppercase |
   | `ticker` | string, up to 32 | NOT NULL, not empty |
   | `name` | string, up to 200 | NOT NULL, not empty |
   | `legal_name` | string, up to 300 | nullable |
   | `created_at` | UTC timestamp | NOT NULL, set when the row is created |
   | `updated_at` | UTC timestamp | NOT NULL, set when the row is created |

   The ISIN, ticker and name rules are database `CHECK` constraints (the last
   line of defence). Full ISIN validation, such as the country prefix and
   check digit, belongs to the API and service layers in step 3. The string
   length limits are documented on the model for portability; SQLite does not
   enforce them.

6. **Migrations.** Alembic manages the investments schema, with its migration
   environment and versions inside the investments module.
   - Migration `0001` creates the `instruments` table and its constraints.
     Its downgrade drops the table.
   - The migration environment reads the database URL from the Alembic
     configuration when one is passed in, and from settings otherwise.
   - A repository-root `alembic.ini` defines an `investments` section, so
     developers can use the standard Alembic command line, for example:
     `uv run alembic -n investments upgrade head` and
     `uv run alembic -n investments revision --autogenerate -m "..."`.
   - A function upgrades the investments database to the latest revision
     for a given URL. The start command and the tests both use it.

7. **Migrations match the models.** A test proves that the database produced
   by running all migrations matches the SQLAlchemy models, using Alembic's
   schema comparison, which must report no differences. A model change
   without a matching migration then fails the test suite.

8. **Instrument repository.** `findash.investments.repository` provides an
   instrument repository that works on a session passed in by the caller.
   The repository never commits; the caller owns the transaction. It
   supports:
   - adding an instrument (ISIN, ticker, name, optional legal name) and
     returning the stored instrument with its ID and timestamps;
   - getting an instrument by ID (returns nothing when missing);
   - getting an instrument by ISIN (returns nothing when missing);
   - listing all instruments, ordered by ID.

   Adding an instrument whose ISIN already exists raises a module-specific
   "instrument already exists" error naming the ISIN, instead of leaking
   SQLAlchemy's `IntegrityError`, and leaves the session usable. Update and
   delete are deliberately absent.

9. **Migrations on start.** `uv run findash` upgrades the investments
   database to the latest revision before starting uvicorn. This creates
   `.data/investments.db` (and `.data/`) on first start. If a migration
   fails, the server does not start and the command exits with an error. The
   existing `--host` and `--port` options keep working. The FastAPI app
   itself doesn't touch the database yet: no endpoints use it in this step.

10. **Tests.** Every test that touches a database uses a fresh SQLite file in
    pytest's temporary directory, migrated with the same upgrade function as
    production. No test reads or writes `.data/`. The default URL is only
    asserted, never opened.

11. **Documentation.** `README.md` and `AGENTS.md` describe:
    - the database location and how to override it;
    - that `uv run findash` applies migrations automatically;
    - how to create and apply migrations with Alembic;
    - the rule that every schema change ships as a migration together with
      its model change.

12. **Local data.** The old `.data/investments.sqlite3` from the retired CLI
    is neither read, modified, nor deleted. The new database file
    (`investments.db`) has a different name.

## Acceptance criteria

- On a fresh clone, these all succeed from the repository root:
  - `uv sync --locked`;
  - `uv run pytest`;
  - `uv run mypy` (strict);
  - `uv run ruff check .`;
  - `uv run ruff format --check .`;
  - `uv run pre-commit run --all-files`.
- Settings tests show:
  - the default `investments_database_url` is
    `sqlite:///.data/investments.db`;
  - setting `FINDASH_INVESTMENTS_DATABASE_URL` overrides it.
- Database helper tests show:
  - the parent directory is created for a file-based SQLite URL;
  - foreign keys are enforced on new connections;
  - the transaction context manager commits on success and rolls back on an
    exception;
  - the UTC timestamp type returns timezone-aware UTC datetimes after a
    round trip.
- Migration tests show:
  - upgrading a fresh database creates `instruments` with the specified
    columns, nullability, unique ISIN and CHECK constraints;
  - upgrading twice is a no-op;
  - downgrading to base removes the table;
  - the migrated schema matches the models (no autogenerate differences).
- Repository tests show:
  - adding an instrument returns it with an ID, `legal_name` stored or
    `None`, and timezone-aware `created_at`/`updated_at`;
  - it can be fetched by ID and by ISIN, and missing IDs or ISINs return
    `None`;
  - listing returns instruments in ID order;
  - a duplicate ISIN raises the "instrument already exists" error, and the
    session can still be used afterwards;
  - nothing is persisted unless the caller commits;
  - inserting an invalid ISIN, an empty ticker or an empty name directly
    violates the database constraints.
- Start-command tests show that migrations run against the configured URL
  before uvicorn starts, and that uvicorn is not started if the migration
  fails.
- Manually, `uv run findash` creates `.data/investments.db` with the
  `instruments` table and an Alembic version table at revision `0001`, and
  `/api/health` still returns `{"status":"ok"}`.
- `uv run alembic -n investments current` reports `0001 (head)` against the
  database `uv run findash` created.
- No new files appear under `data/`, `.data/investments.sqlite3` is unchanged,
  and no database file is committed.

## Out of scope

- Instrument services and API endpoints, ISIN check-digit validation, and the
  structured error format (step 3).
- Trades, dividends and holdings tables, and their logic (steps 4-6).
- Update and delete operations.
- Other modules' databases (expenses, crypto), async database access, and
  connection pooling tuning.
- PostgreSQL support beyond keeping the code database-agnostic (no
  PostgreSQL driver or testing).
- Seeding or importing data, and migrating data from the old CLI database.

## Implementation plan: individual commits

1. **`build: add database dependencies and settings`**
   - **Purpose:** add SQLAlchemy, Alembic and pydantic-settings (`<2.16`),
     and implement `findash.core.settings`. Addresses requirements 1 and 2.
   - **Scope:** dependencies and settings only.
   - **Tests:** default database URL; environment variable override; explicit
     construction without the environment.
   - **Verify:** `uv sync --locked`, `uv run pytest`, `uv run mypy`.

2. **`feat(core): add database engine, session, and UTC timestamp helpers`**
   - **Purpose:** add the engine factory (SQLite parent directory creation and
     foreign-key pragma), the session factory, the transaction context
     manager, and the UTC timestamp type. Addresses requirement 3.
   - **Scope:** `findash.core.database` only, with no tables.
   - **Tests:** directory creation; `PRAGMA foreign_keys` returns 1; commit on
     success; rollback on exception; timezone-aware UTC round trip using a
     test-only table.
   - **Verify:** `uv run pytest`, `uv run mypy`.

3. **`feat(investments): add the instruments schema and first migration`**
   - **Purpose:** add the investments declarative base and `Instrument`
     model, the Alembic environment inside the module, the repository-root
     `alembic.ini` with the `investments` section, migration `0001`, and the
     upgrade-to-head function. Addresses requirements 4-7 and 10.
     Depends on commit 2.
   - **Scope:** schema and migrations only; no repository yet.
   - **Tests:** columns, nullability and constraints after upgrade; repeated
     upgrade; downgrade; migrations match the models; CHECK and UNIQUE
     violations on direct inserts.
   - **Verify:** `uv run pytest`, `uv run mypy`, and
     `uv run alembic -n investments upgrade head` against a temporary URL.

4. **`feat(investments): add the instrument repository`**
   - **Purpose:** add, get by ID, get by ISIN, and list instruments, with the
     duplicate-ISIN error. Addresses requirement 8. Depends on commit 3.
   - **Scope:** data access only; no services or endpoints.
   - **Tests:** every repository behaviour listed in the acceptance criteria,
     against migrated temporary databases.
   - **Verify:** `uv run pytest`, `uv run mypy`.

5. **`feat(api): apply migrations when the server starts`**
   - **Purpose:** make `uv run findash` upgrade the configured investments
     database before starting uvicorn. Addresses requirement 9.
     Depends on commit 3.
   - **Scope:** start command only.
   - **Tests:** with the migration and uvicorn functions monkeypatched,
     migrations run with the configured URL before uvicorn; a migration
     failure stops uvicorn from starting; host and port options still apply.
   - **Verify:** `uv run pytest`, plus a manual `uv run findash` that creates
     `.data/investments.db`.

6. **`docs: document the database and migration workflow`**
   - **Purpose:** update `README.md` and `AGENTS.md` (database location and
     override, automatic migrations, Alembic commands, and the "model change
     ships with a migration" rule). Addresses requirement 11.
   - **Scope:** documentation only.
   - **Verify:** `uv run pytest`, `uv run mypy`, `uv run ruff check .`,
     `uv run ruff format --check .`.

## Verification notes

- Repeat the full acceptance list on a fresh clone of the branch. Then start
  `uv run findash` in that clone and inspect the created database (tables
  and Alembic revision) to prove that automatic migration works end to end.
- Check release ages again at implementation time and record the final
  versions, plus any held-back transitive packages, in the PR description.
- Confirm with `git status` that `.data/` and `data/` contain no tracked
  changes, and that `.data/investments.sqlite3` keeps its original size and
  modification time.

## Open questions

- None. All schema and architecture choices were confirmed during planning.
  This PRD makes these technical choices, which can be revisited in review:
  - string length limits of 12, 32, 200 and 300;
  - instruments listed in ID order;
  - a repository-root `alembic.ini` with one section per module.
