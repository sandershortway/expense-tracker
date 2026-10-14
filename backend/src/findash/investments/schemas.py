from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from findash.investments.isin import is_valid_isin


def _check_isin(value: str) -> str:
    if not is_valid_isin(value):
        raise ValueError(
            "not a valid ISIN: expected 2 letters, 9 letters or digits, "
            "and a matching check digit"
        )
    return value


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


Isin = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True),
    AfterValidator(_check_isin),
    Field(examples=["US67066G1040"]),
]
Ticker = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, min_length=1, max_length=32
    ),
    Field(examples=["NVDA"]),
]
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    Field(examples=["Nvidia"]),
]
LegalName = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
    | None,
    BeforeValidator(_blank_to_none),
    Field(examples=["NVIDIA Corporation"]),
]


class InstrumentCreate(BaseModel):
    """Input for creating an instrument."""

    model_config = ConfigDict(extra="forbid")

    isin: Isin
    ticker: Ticker
    name: Name
    legal_name: LegalName = None


class InstrumentRead(BaseModel):
    """An instrument as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    isin: str
    ticker: str
    name: str
    legal_name: str | None
    created_at: datetime
    updated_at: datetime
