from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker


def get_investments_session(request: Request) -> Iterator[Session]:
    """One session per request; closing it rolls back anything uncommitted."""
    factory: sessionmaker[Session] = (
        request.app.state.investments_session_factory
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()


InvestmentsSession = Annotated[Session, Depends(get_investments_session)]
