# PRD-001: Establish the Python Project Foundation

**Priority:** First project milestone; the repository is currently empty.
**Area:** Python tooling, developer workflow, automated checks.
**Dependencies:** None.

## Problem

The repository needs a reproducible Python development setup before application work begins. Developers should be able to create and synchronize the environment with `uv`, format consistently with Ruff, run the test suite, and have formatting and tests run as part of the pre-commit workflow.

## User story

As a contributor, I want a documented, reproducible Python project setup with automated formatting and tests, so that future application changes start from a consistent and verifiable baseline.

## Requirements

1. The project must use `uv` for Python project and environment management, with dependency metadata and a committed lockfile so that a fresh checkout can be synchronized reproducibly.
2. Ruff must be the formatter, with a 79-character line length and Python style settings chosen to align with PEP 8. The configured lint checks must catch the baseline error classes selected for the project.
3. The repository must define a test suite and a documented command to run it through `uv`. The initial suite must include at least one test proving the test runner is wired correctly.
4. The repository must provide a tracked pre-commit configuration and setup instructions. After hook installation, a commit attempt must format staged Python files and run the full test suite. If formatting changes staged files, the hook must prevent the commit until those changes are staged.
5. The documented setup and verification commands must work from a fresh checkout using the committed project configuration and lockfile.
6. This milestone must not implement expense-tracking behavior, database schema, CSV import, or application interfaces.

## Acceptance criteria

- A contributor can install the declared development dependencies from a fresh checkout using `uv` and the committed lockfile without manually creating or activating a virtual environment.
- The configured Ruff command formats the project's Python files and the Ruff lint command passes on the baseline code.
- The documented test command executes the initial test suite successfully.
- After following the documented hook-installation step, attempting a commit runs formatting before the full test suite; a formatter change is detected by the hook and requires restaging before the commit can proceed.
- Setup, formatting, linting, test, and hook-installation commands are documented and use `uv run` where applicable.

## Out of scope

- Expense tracker domain models, database schema, persistence, and CRUD operations.
- CSV or PDF importing, transaction categorization, or LLM integration.
- Application UI, API, deployment, and production configuration.
- CI workflows and publishing or packaging the application for distribution.

## Implementation plan: individual commits

1. **`Establish reproducible uv project metadata`** — Create the minimal Python project configuration, declare development tooling, and generate the lockfile. Addresses requirements 1 and 5. Scope: project metadata and dependency declarations only. Tests: none; verify clean dependency resolution. Verify: `uv sync --locked`.
2. **`Configure Ruff and the initial test suite`** — Set the PEP 8-oriented Ruff formatting and lint configuration, add the selected test runner and a minimal smoke test. Addresses requirements 2 and 3. Scope: tooling configuration and baseline test only. Tests: the smoke test plus Ruff lint/format checks. Verify: `uv run ruff format --check .`, `uv run ruff check .`, and `uv run pytest`.
3. **`Add pre-commit automation and setup instructions`** — Add a tracked pre-commit configuration that formats staged Python files and runs the complete test suite, plus concise fresh-checkout instructions including hook installation. Addresses requirements 4 and 5. Scope: hook configuration and developer setup documentation. Tests: verify hook behavior for a formatting change and a passing/failing test suite. Verify: `uv run pre-commit run --all-files` and a local test commit using the installed hook.

## Verification notes

- The pre-commit configuration must be tested with a real Git commit attempt in a disposable local test state to verify that formatter edits require restaging and that test failures block commits. No remote push is required.
- The project targets Python 3.15, the latest stable Python release (3.15.0, released Oct. 9, 2026), and pytest is the selected test framework.
- Because Python 3.15.0 is newly released, implementation must verify that the selected tool versions support it. If Ruff, pytest, or pre-commit lacks compatible releases, document the fallback version constraint before proceeding.
