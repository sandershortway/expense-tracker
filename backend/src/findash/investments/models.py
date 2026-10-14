from datetime import datetime

from sqlalchemy import CheckConstraint, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from findash.core.database import UTCDateTime, utc_now

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every table in the investments database."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Instrument(Base):
    """A stock or ETF, identified by its ISIN."""

    __tablename__ = "instruments"
    __table_args__ = (
        CheckConstraint(
            "length(isin) = 12 AND isin = upper(isin)", name="isin_format"
        ),
        CheckConstraint("length(trim(ticker)) > 0", name="ticker_not_empty"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True)
    ticker: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
