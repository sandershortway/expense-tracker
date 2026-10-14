from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from findash.investments.errors import InstrumentAlreadyExists
from findash.investments.models import Instrument


class InstrumentRepository:
    """Data access for instruments. The caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        isin: str,
        ticker: str,
        name: str,
        legal_name: str | None = None,
    ) -> Instrument:
        instrument = Instrument(
            isin=isin, ticker=ticker, name=name, legal_name=legal_name
        )
        try:
            with self._session.begin_nested():
                self._session.add(instrument)
        except IntegrityError as error:
            if self.get_by_isin(isin) is not None:
                raise InstrumentAlreadyExists(isin) from error
            raise
        return instrument

    def get(self, instrument_id: int) -> Instrument | None:
        return self._session.get(Instrument, instrument_id)

    def get_by_isin(self, isin: str) -> Instrument | None:
        return self._session.scalars(
            select(Instrument).where(Instrument.isin == isin)
        ).one_or_none()

    def list(self) -> Sequence[Instrument]:
        return self._session.scalars(
            select(Instrument).order_by(Instrument.id)
        ).all()
