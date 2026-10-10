# expense-tracker

A personal expense tracking application. Currently at project-foundation
stage: reproducible `uv` environment, Ruff formatting/linting, pytest, and
pre-commit automation.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) **0.13.0 or newer** (required for managed
  CPython 3.15; check with `uv --version`, upgrade with `uv self update`).

## Setup

From a fresh checkout:

```sh
uv sync
```

`uv` automatically downloads CPython 3.15 (per `.python-version`), creates
`.venv`, and installs the locked dev dependencies — no manual virtual
environment or activation needed.

Install the pre-commit hooks:

```sh
uv run pre-commit install
```

## Commands

| Task             | Command                    |
| ---------------- | -------------------------- |
| Sync environment | `uv sync`                  |
| Format code      | `uv run ruff format .`     |
| Lint             | `uv run ruff check .`      |
| Run tests        | `uv run pytest`            |
| Install hooks    | `uv run pre-commit install`|

## Pre-commit behavior

Each commit runs, in order:

1. **ruff format** — reformats staged Python files. If formatting changes a
   file, the commit is blocked until the changes are re-staged.
2. **ruff check** — lints staged Python files.
3. **pytest** — runs the full test suite on every commit.

Hooks invoke `uv run`, so they use the same locked tool versions as manual
commands.
