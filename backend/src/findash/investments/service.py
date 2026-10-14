from collections.abc import Sequence

from sqlalchemy.orm import Session

from findash.investments.errors import InstrumentNotFound
from findash.investments.models import Instrument
from findash.investments.repository import InstrumentRepository


class InstrumentService:
    """Business operations on instruments; commits successful writes."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._instruments = InstrumentRepository(session)

    def create(
        self,
        *,
        isin: str,
        ticker: str,
        name: str,
        legal_name: str | None = None,
    ) -> Instrument:
        instrument = self._instruments.add(
            isin=isin, ticker=ticker, name=name, legal_name=legal_name
        )
        self._session.commit()
        return instrument

    def get(self, instrument_id: int) -> Instrument:
        instrument = self._instruments.get(instrument_id)
        if instrument is None:
            raise InstrumentNotFound(instrument_id)
        return instrument

    def list(self) -> Sequence[Instrument]:
        return self._instruments.list()
