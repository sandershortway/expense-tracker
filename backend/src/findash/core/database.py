from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Connection,
    DateTime,
    Engine,
    create_engine,
    event,
    make_url,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator


def create_database_engine(url: str) -> Engine:
    """Create an engine; prepares SQLite files and enables foreign keys."""
    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    if is_sqlite and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(parsed)
    if is_sqlite:
        event.listen(engine, "connect", _configure_sqlite_connection)
        event.listen(engine, "begin", _begin_sqlite_transaction)
    return engine


def _configure_sqlite_connection(dbapi_connection: Any, _: Any) -> None:
    # Stop the sqlite3 driver from managing transactions itself, so that
    # SQLAlchemy's BEGIN, SAVEPOINT, and ROLLBACK behave as documented.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _begin_sqlite_transaction(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session; commit on success, roll back on error, then close."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes, stored as naive UTC for portability."""

    impl = DateTime()
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
