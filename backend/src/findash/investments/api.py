from typing import Any

from fastapi import APIRouter, Request, Response, status

from findash.core.errors import ErrorResponse
from findash.investments.dependencies import InvestmentsSession
from findash.investments.schemas import InstrumentCreate, InstrumentRead
from findash.investments.service import InstrumentService

router = APIRouter(prefix="/api/investments", tags=["investments"])

_CONFLICT: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "An instrument with this ISIN already exists",
    }
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "The instrument does not exist",
    }
}


@router.post(
    "/instruments",
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
)
def create_instrument(
    payload: InstrumentCreate,
    session: InvestmentsSession,
    request: Request,
    response: Response,
) -> InstrumentRead:
    instrument = InstrumentService(session).create(**payload.model_dump())
    response.headers["Location"] = request.app.url_path_for(
        "get_instrument", instrument_id=str(instrument.id)
    )
    return InstrumentRead.model_validate(instrument)


@router.get("/instruments")
def list_instruments(session: InvestmentsSession) -> list[InstrumentRead]:
    instruments = InstrumentService(session).list()
    return [InstrumentRead.model_validate(i) for i in instruments]


@router.get("/instruments/{instrument_id}", responses=_NOT_FOUND)
def get_instrument(
    instrument_id: int, session: InvestmentsSession
) -> InstrumentRead:
    instrument = InstrumentService(session).get(instrument_id)
    return InstrumentRead.model_validate(instrument)
