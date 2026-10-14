from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from findash.investments.database import alembic_config, upgrade_database
from findash.investments.models import Base

TIMESTAMP = "2026-10-14 12:00:00"


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def insert_instrument(engine: Engine, **overrides: Any) -> None:
    values = {
        "isin": "US67066G1040",
        "ticker": "NVDA",
        "name": "Nvidia",
        "legal_name": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO instruments (isin, ticker, name, legal_name, "
                "created_at, updated_at) VALUES (:isin, :ticker, :name, "
                ":legal_name, :created_at, :updated_at)"
            ),
            values,
        )


def test_upgrade_creates_instruments_table(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("instruments")}

    assert current_revision(engine) == "0001"
    assert list(columns) == [
        "id",
        "isin",
        "ticker",
        "name",
        "legal_name",
        "created_at",
        "updated_at",
    ]
    assert {name: c["nullable"] for name, c in columns.items()} == {
        "id": False,
        "isin": False,
        "ticker": False,
        "name": False,
        "legal_name": True,
        "created_at": False,
        "updated_at": False,
    }
    assert inspector.get_pk_constraint("instruments")[
        "constrained_columns"
    ] == ["id"]
    assert [
        u["column_names"]
        for u in inspector.get_unique_constraints("instruments")
    ] == [["isin"]]
    assert {
        c["name"] for c in inspector.get_check_constraints("instruments")
    } == {
        "ck_instruments_isin_format",
        "ck_instruments_ticker_not_empty",
        "ck_instruments_name_not_empty",
    }


def test_upgrade_is_idempotent(engine: Engine, database_url: str) -> None:
    upgrade_database(database_url)

    assert current_revision(engine) == "0001"


def test_downgrade_removes_instruments_table(
    engine: Engine, database_url: str
) -> None:
    command.downgrade(alembic_config(database_url), "base")

    assert "instruments" not in inspect(engine).get_table_names()
    assert current_revision(engine) is None


def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        differences = compare_metadata(context, Base.metadata)

    assert differences == []


def test_valid_row_satisfies_constraints(engine: Engine) -> None:
    insert_instrument(engine, legal_name="NVIDIA Corporation")


@pytest.mark.parametrize(
    "overrides",
    [
        {"isin": "US67066G104"},
        {"isin": "us67066g1040"},
        {"ticker": ""},
        {"ticker": "   "},
        {"name": ""},
        {"ticker": None},
        {"name": None},
        {"isin": None},
    ],
)
def test_constraints_reject_invalid_rows(
    engine: Engine, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        insert_instrument(engine, **overrides)


def test_isin_must_be_unique(engine: Engine) -> None:
    insert_instrument(engine)

    with pytest.raises(IntegrityError):
        insert_instrument(engine, ticker="NVD")
