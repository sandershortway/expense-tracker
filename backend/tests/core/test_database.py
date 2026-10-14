from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine, String, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from findash.core.database import (
    UTCDateTime,
    create_database_engine,
    create_session_factory,
    transaction,
)


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(50))
    at: Mapped[datetime | None] = mapped_column(UTCDateTime())


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def count_notes(engine: Engine) -> int:
    with engine.connect() as connection:
        count = connection.scalar(text("SELECT count(*) FROM notes"))
    assert isinstance(count, int)
    return count


def test_creates_parent_directory_for_sqlite_file(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "dir" / "app.db"

    engine = create_database_engine(f"sqlite:///{database}")
    with engine.connect():
        pass
    engine.dispose()

    assert database.exists()


def test_sqlite_connections_enforce_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        enabled = connection.execute(text("PRAGMA foreign_keys")).one()[0]

    assert enabled == 1


def test_transaction_commits_on_success(engine: Engine) -> None:
    with transaction(create_session_factory(engine)) as session:
        session.add(Note(text="kept"))

    assert count_notes(engine) == 1


def test_transaction_rolls_back_on_error(engine: Engine) -> None:
    with pytest.raises(RuntimeError):
        with transaction(create_session_factory(engine)) as session:
            session.add(Note(text="discarded"))
            session.flush()
            raise RuntimeError("boom")

    assert count_notes(engine) == 0


def test_objects_stay_readable_after_commit(engine: Engine) -> None:
    with transaction(create_session_factory(engine)) as session:
        note = Note(text="readable")
        session.add(note)

    assert note.text == "readable"
    assert note.id == 1


def test_utc_datetime_round_trips_as_aware_utc(engine: Engine) -> None:
    amsterdam = timezone(timedelta(hours=2))
    stored = datetime(2026, 10, 14, 21, 30, tzinfo=amsterdam)
    factory = create_session_factory(engine)
    with transaction(factory) as session:
        session.add(Note(text="time", at=stored))

    with transaction(factory) as session:
        loaded = session.scalars(select(Note.at)).one()

    assert loaded == datetime(2026, 10, 14, 19, 30, tzinfo=UTC)
    assert loaded is not None and loaded.tzinfo is UTC


def test_utc_datetime_rejects_naive_datetimes(engine: Engine) -> None:
    with pytest.raises(StatementError, match="timezone-aware"):
        with transaction(create_session_factory(engine)) as session:
            session.add(Note(text="naive", at=datetime(2026, 10, 14, 12)))
