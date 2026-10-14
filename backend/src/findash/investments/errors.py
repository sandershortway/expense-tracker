from findash.core.errors import ConflictError, NotFoundError


class InstrumentAlreadyExists(ConflictError):
    def __init__(self, isin: str) -> None:
        super().__init__(
            "instrument_exists",
            f"an instrument with ISIN {isin} already exists",
        )
        self.isin = isin


class InstrumentNotFound(NotFoundError):
    def __init__(self, instrument_id: int) -> None:
        super().__init__(
            "instrument_not_found",
            f"instrument {instrument_id} was not found",
        )
        self.instrument_id = instrument_id
