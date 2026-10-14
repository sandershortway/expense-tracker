# PRD-008: Create, List, and Look Up Instruments Through the API

**Priority:** Step 3 of the financial-dashboard plan; the first feature
endpoint. Trades and dividends (steps 4-5) reference instruments by ID.
**Area:** Investments service and API layers, ISIN validation, shared error
handling, and wiring database sessions into the app.
**Dependencies:** PRD-007 (investments database and instrument repository).
**Status note:** On `main` at `4d21f55`, the investments database has an
`instruments` table (migration `0001`). Its repository supports add, get by
ID, get by ISIN, and list, and raises `InstrumentAlreadyExists` for a
duplicate ISIN. The FastAPI app exposes only `GET /api/health`. It is created
at import time (`findash.main:app`) and doesn't touch the database. There are
44 passing tests. The planning decisions this PRD relies on were all
confirmed by the user:

- endpoints live under `/api/investments/...`;
- validation happens in three layers: the API checks shape and format, the
  service checks rules that need the database, and database constraints are
  the last safety net;
- business errors use one shape, `{"error": {"code", "message"}}`, with
  404 for something that doesn't exist and 409 for conflicts, while
  FastAPI's default 422 shape is kept for invalid input;
- integer IDs;
- create and read only.

## Problem

Instruments can only be created from Python code today. To use the dashboard,
and later to call it from a frontend, instruments must be creatable and
readable over HTTP. The API also needs a few things that don't exist yet:

- **ISIN validation.** A real ISIN has a fixed format and a check digit.
  Without validation, typos such as a single wrong digit are stored
  permanently, because there is no edit or delete yet.
- **Consistent errors.** The frontend needs predictable error responses to
  show useful messages.
- **A service layer.** Business rules belong between the API and the
  repository, not in the endpoint functions.
- **Request-scoped database sessions.** Each request needs its own session,
  and tests must be able to point the app at a temporary database.

## User story

As the user of my financial dashboard, I want to create instruments and look
them up through the API, with clear errors for invalid or duplicate input, so
that I can build up my list of stocks and ETFs from the interactive docs now
and from the frontend later.

## Requirements

1. **ISIN validation** (`findash.investments.isin`). A function decides
   whether a string is a valid ISIN:
   - exactly 12 characters;
   - a 2-letter country prefix;
   - 9 letters or digits;
   - 1 check digit that matches the standard ISIN check-digit calculation
     (letters converted to numbers A=10 to Z=35, then the Luhn algorithm).

   It accepts real ISINs such as `US0378331005`, `US67066G1040`,
   `NL0010273215`, `IE00B5BMR087` and `FR0010717090`. It rejects wrong
   lengths, lowercase input that hasn't been normalised, invalid characters,
   and a wrong check digit (for example `US0378331006`). It does not check
   whether the country prefix is a real country code.

2. **Structured errors** (`findash.core.errors`).
   - A base application error carries a machine-readable `code` and a
     human-readable `message`.
   - Two kinds of error exist: "not found" (HTTP 404) and "conflict"
     (HTTP 409).
   - An exception handler, registered by the app factory, turns any
     application error into its HTTP status with the body
     `{"error": {"code": "<code>", "message": "<message>"}}`.
   - Request validation errors keep FastAPI's default 422 response.
   - Modules define their own errors as subclasses. The core package doesn't
     know about any module.

3. **Instrument errors** (`findash.investments.errors`).
   - `InstrumentAlreadyExists` is a conflict with code `instrument_exists`,
     and its message names the ISIN. It moves here from the repository
     module; the repository keeps raising it.
   - `InstrumentNotFound` is a not-found error with code
     `instrument_not_found`, and its message names the ID.

4. **Instrument service** (`findash.investments.service`). The service works
   on a session passed in by the caller and owns the transaction for write
   operations: it commits after a successful create. It provides:
   - **create**: ISIN, ticker, name and optional legal name; returns the
     stored instrument. A duplicate ISIN raises `InstrumentAlreadyExists`,
     and nothing is committed.
   - **get by ID**: raises `InstrumentNotFound` when the instrument is
     missing.
   - **list**: returns all instruments in ID order.

   The service assumes its input is already validated by the API layer, and
   doesn't repeat format checks.

5. **App factory and database sessions** (`findash.main`).
   - `create_app()` takes optional settings; without them it reads the
     settings from the environment.
   - Creating the app opens no database connection and creates no files.
     The engine and session factory are created when the app starts and
     disposed when it shuts down, using FastAPI's lifespan.
   - A request-scoped dependency provides one session per request. The
     session is closed afterwards and rolled back if an error occurs.
   - The module-level `app` object is removed. `uv run findash` starts
     uvicorn in factory mode (`findash.main:create_app`), after the
     migrations from PRD-007 have run.
   - `GET /api/health` and `/docs` keep working, and the health check
     doesn't need the database.

6. **Request and response schemas** (`findash.investments.schemas`), using
   Pydantic.

   For creating an instrument:

   | Field | Rules |
   |---|---|
   | `isin` | required; surrounding whitespace removed and converted to uppercase, then validated as in requirement 1 |
   | `ticker` | required; whitespace removed and converted to uppercase; 1-32 characters |
   | `name` | required; whitespace removed; 1-200 characters |
   | `legal_name` | optional; whitespace removed; up to 300 characters; empty or missing becomes `null` |

   Unknown fields are rejected.

   An instrument response contains `id`, `isin`, `ticker`, `name`,
   `legal_name`, `created_at` and `updated_at`, with the timestamps as
   ISO 8601 UTC strings.

7. **Endpoints** (`findash.investments.api`, mounted under
   `/api/investments`).

   | Request | Success | Errors |
   |---|---|---|
   | `POST /api/investments/instruments` | 201 with the instrument, plus a `Location` header pointing to it | 422 for invalid input; 409 `instrument_exists` for a duplicate ISIN |
   | `GET /api/investments/instruments` | 200 with a JSON array of instruments in ID order (`[]` when empty) | none |
   | `GET /api/investments/instruments/{instrument_id}` | 200 with the instrument | 404 `instrument_not_found`; 422 for a non-integer ID |

   Endpoint functions only translate between HTTP and the service: no
   queries and no business rules. Every endpoint appears in `/docs` with its
   request and response schemas, and with the 404 and 409 error responses
   documented.

8. **Tests.** Every database-backed test uses a fresh, migrated SQLite
   database in pytest's temporary directory. API tests run the app inside a
   `TestClient` context, so lifespan runs, with settings pointing at that
   database. No test creates `.data/`.

9. **Documentation.** `README.md` documents the instrument endpoints with an
   example request and response, the error format, and how to try the
   endpoints in `/docs`. `AGENTS.md` records the layering rules:
   - endpoints call services and contain no queries or rules;
   - services own write transactions;
   - repositories never commit;
   - module errors subclass the core error types.

## Acceptance criteria

- On a fresh clone, these all succeed from the repository root:
  - `uv sync --locked`;
  - `uv run pytest`;
  - `uv run mypy`;
  - `uv run ruff check .`;
  - `uv run ruff format --check .`;
  - `uv run pre-commit run --all-files`.
- ISIN tests cover the valid examples above and each rejection case.
- Error tests show that application errors produce the documented status
  and body, and that validation errors keep FastAPI's 422 shape.
- Service tests show:
  - create commits, and the instrument is readable from a new session;
  - a duplicate ISIN raises `InstrumentAlreadyExists` and leaves the
    database unchanged;
  - a missing ID raises `InstrumentNotFound`;
  - list returns instruments in ID order.
- API tests show:
  - **create** returns 201 with the stored body, a `Location` header,
    ISIN and ticker normalised to uppercase, whitespace removed, and blank
    `legal_name` turned into `null`;
  - **invalid ISIN** (bad check digit or format), a missing or empty
    required field, a field that is too long, or an unknown field returns
    422, and nothing is stored;
  - **duplicate ISIN** returns 409 with
    `{"error": {"code": "instrument_exists", ...}}`;
  - **list** returns instruments in ID order, and `[]` on an empty
    database;
  - **get** returns the instrument, 404 with code `instrument_not_found`
    for an unknown ID, and 422 for a non-integer ID;
  - **persistence**: data created in one app instance is visible from a new
    app instance on the same database.
- Creating the app without starting it doesn't create the database file or
  `.data/`.
- The start command still runs migrations before uvicorn, and now starts
  uvicorn in factory mode with the configured host and port.
- Manually, after `uv run findash`, creating an instrument from `/docs` and
  listing it works, and the data is still there after a restart.

## Out of scope

- Updating or deleting instruments.
- Trades, dividends and holdings (steps 4-6).
- Filtering, searching, sorting options and pagination for the list.
- Checking that an ISIN's country prefix is an assigned country code, or
  looking up instrument data online.
- Authentication, CORS and frontend work.
- Changing the database schema (no migration in this step).

## Implementation plan: individual commits

1. **`feat(investments): validate ISINs`**
   - **Purpose:** ISIN format and check-digit validation. Addresses
     requirement 1.
   - **Scope:** a pure function with no framework code.
   - **Tests:** parametrised valid ISINs; wrong length; lowercase; invalid
     characters; letters in the check-digit position; a wrong check digit.
   - **Verify:** `uv run pytest`, `uv run mypy`.

2. **`feat(core): add structured application errors`**
   - **Purpose:** the base, not-found and conflict error types, and the
     exception handler. Addresses requirement 2.
   - **Scope:** `findash.core.errors` only.
   - **Tests:** a minimal test app raising each error kind returns the
     correct status and body; a request validation error still returns
     FastAPI's 422 shape.
   - **Verify:** `uv run pytest`, `uv run mypy`.

3. **`feat(investments): add the instrument service`**
   - **Purpose:** instrument errors (moving `InstrumentAlreadyExists`), and
     the service with create, get and list. Addresses requirements 3 and 4.
     Depends on commit 2.
   - **Scope:** service and errors; the repository only changes its import.
   - **Tests:** every service behaviour in the acceptance criteria; the
     existing repository tests keep passing.
   - **Verify:** `uv run pytest`, `uv run mypy`.

4. **`feat(api): provide database sessions to requests`**
   - **Purpose:** `create_app(settings)`, a lifespan that creates and disposes
     the engine, the request session dependency, the error handler
     registration, removing the module-level `app`, and factory mode in the
     start command. Addresses requirement 5. Depends on commit 2.
   - **Scope:** app wiring; no new endpoints.
   - **Tests:** creating the app opens no database; lifespan creates and
     disposes the engine; the session dependency yields a working session
     against a temporary database; health and docs still work; the start
     command migrates, then calls uvicorn with `factory=True` and the
     configured host and port.
   - **Verify:** `uv run pytest`, `uv run mypy`, plus a manual
     `uv run findash` health check.

5. **`feat(investments): add instrument endpoints`**
   - **Purpose:** request and response schemas, the router with
     `POST`/`GET`/`GET {id}`, mounted in the app factory. Addresses
     requirements 6 and 7. Depends on commits 1, 3 and 4.
   - **Scope:** API layer only.
   - **Tests:** every API behaviour in the acceptance criteria, including
     persistence across app instances and the OpenAPI schema listing the
     three operations.
   - **Verify:** `uv run pytest`, `uv run mypy`, plus a manual walkthrough in
     `/docs`.

6. **`docs: document the instruments API and layering rules`**
   - **Purpose:** README endpoint and error documentation; AGENTS.md
     layering rules. Addresses requirement 9.
   - **Scope:** documentation only.
   - **Verify:** `uv run pytest`, `uv run mypy`, `uv run ruff check .`,
     `uv run ruff format --check .`.

## Verification notes

- Repeat the acceptance list on a fresh clone. Then run `uv run findash` in
  that clone, create an instrument with a real HTTP request, list it,
  restart, and list it again, to prove that data persists through the
  running server.
- No new dependencies are expected: Pydantic comes with FastAPI. If one turns
  out to be needed, apply the 7-day release rule and note it in the PR.
- Confirm that `.data/` and `data/` in the main working copy stay unchanged.

## Open questions

- None. This PRD makes these technical choices, which can be revisited in
  review:
  - ISIN and ticker are converted to uppercase and stripped of whitespace,
    rather than rejected when they're lowercase;
  - a blank `legal_name` is stored as `null`;
  - `POST` returns a `Location` header;
  - the service, not the request, owns the commit, so a failed commit can
    never be reported as a success.
