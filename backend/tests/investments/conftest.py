from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from findash.core.database import create_database_engine
from findash.investments.database import upgrade_database


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'investments.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """A fresh investments database migrated to the latest revision."""
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    yield engine
    engine.dispose()
