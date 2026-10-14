from collections.abc import Iterator
from datetime import UTC

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from findash.core.database import create_session_factory, transaction
from findash.investments.models import Instrument
from findash.investments.repository import (
    InstrumentAlreadyExists,
    InstrumentRepository,
)

NVIDIA = {"isin": "US67066G1040", "ticker": "NVDA", "name": "Nvidia"}
ASML = {
    "isin": "NL0010273215",
    "ticker": "ASML",
    "name": "ASML",
    "legal_name": "ASML Holding N.V.",
}


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session = create_session_factory(engine)()
    yield session
    session.close()


def count_instruments(engine: Engine) -> int:
    with create_session_factory(engine)() as session:
        return (
            session.scalar(select(func.count()).select_from(Instrument)) or 0
        )


def test_add_returns_stored_instrument(session: Session) -> None:
    instrument = InstrumentRepository(session).add(**ASML)

    assert instrument.id == 1
    assert instrument.isin == "NL0010273215"
    assert instrument.ticker == "ASML"
    assert instrument.name == "ASML"
    assert instrument.legal_name == "ASML Holding N.V."
    assert instrument.created_at.tzinfo is UTC
    assert instrument.updated_at.tzinfo is UTC


def test_legal_name_is_optional(session: Session) -> None:
    assert InstrumentRepository(session).add(**NVIDIA).legal_name is None


def test_get_by_id_and_isin(session: Session) -> None:
    repository = InstrumentRepository(session)
    added = repository.add(**NVIDIA)

    assert repository.get(added.id) is added
    assert repository.get_by_isin("US67066G1040") is added
    assert repository.get(999) is None
    assert repository.get_by_isin("NL0000000000") is None


def test_list_returns_instruments_in_id_order(session: Session) -> None:
    repository = InstrumentRepository(session)
    nvidia = repository.add(**NVIDIA)
    asml = repository.add(**ASML)

    assert repository.list() == [nvidia, asml]


def test_list_is_empty_for_new_database(session: Session) -> None:
    assert InstrumentRepository(session).list() == []


def test_duplicate_isin_raises_and_keeps_session_usable(
    session: Session, engine: Engine
) -> None:
    repository = InstrumentRepository(session)
    repository.add(**NVIDIA)

    with pytest.raises(InstrumentAlreadyExists, match="US67066G1040"):
        repository.add(**{**NVIDIA, "ticker": "NVD"})

    repository.add(**ASML)
    session.commit()
    assert [i.isin for i in repository.list()] == [
        "US67066G1040",
        "NL0010273215",
    ]
    assert count_instruments(engine) == 2


def test_constraint_violation_is_not_reported_as_duplicate(
    session: Session,
) -> None:
    with pytest.raises(IntegrityError):
        InstrumentRepository(session).add(**{**NVIDIA, "isin": "short"})


def test_nothing_persists_without_commit(
    session: Session, engine: Engine
) -> None:
    InstrumentRepository(session).add(**NVIDIA)
    session.rollback()

    assert count_instruments(engine) == 0


def test_committed_instrument_is_readable_in_new_session(
    engine: Engine,
) -> None:
    factory = create_session_factory(engine)
    with transaction(factory) as session:
        InstrumentRepository(session).add(**ASML)

    with transaction(factory) as session:
        loaded = InstrumentRepository(session).get_by_isin("NL0010273215")

    assert loaded is not None
    assert loaded.legal_name == "ASML Holding N.V."
    assert loaded.created_at.tzinfo is UTC
