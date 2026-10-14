from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from findash.core.database import create_session_factory
from findash.investments.errors import (
    InstrumentAlreadyExists,
    InstrumentNotFound,
)
from findash.investments.service import InstrumentService

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


def new_service(engine: Engine) -> InstrumentService:
    return InstrumentService(create_session_factory(engine)())


def test_create_commits_the_instrument(
    session: Session, engine: Engine
) -> None:
    created = InstrumentService(session).create(**ASML)

    loaded = new_service(engine).get(created.id)
    assert loaded.isin == "NL0010273215"
    assert loaded.legal_name == "ASML Holding N.V."


def test_duplicate_isin_raises_and_stores_nothing_new(
    session: Session, engine: Engine
) -> None:
    service = InstrumentService(session)
    service.create(**NVIDIA)

    with pytest.raises(InstrumentAlreadyExists) as error:
        service.create(**{**NVIDIA, "ticker": "NVD"})

    assert error.value.code == "instrument_exists"
    assert [i.ticker for i in new_service(engine).list()] == ["NVDA"]


def test_get_missing_instrument_raises_not_found(session: Session) -> None:
    with pytest.raises(InstrumentNotFound) as error:
        InstrumentService(session).get(42)

    assert error.value.code == "instrument_not_found"
    assert "42" in error.value.message


def test_list_returns_instruments_in_id_order(session: Session) -> None:
    service = InstrumentService(session)
    nvidia = service.create(**NVIDIA)
    asml = service.create(**ASML)

    assert [i.id for i in service.list()] == [nvidia.id, asml.id]


def test_list_is_empty_for_new_database(session: Session) -> None:
    assert InstrumentService(session).list() == []
