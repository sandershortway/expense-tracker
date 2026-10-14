from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import text

from findash.__main__ import main
from findash.core.settings import Settings
from findash.investments.dependencies import InvestmentsSession
from findash.main import create_app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "investments.db"


@pytest.fixture
def settings(database_path: Path) -> Settings:
    return Settings(investments_database_url=f"sqlite:///{database_path}")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def start_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Record migration and uvicorn calls made by the start command."""
    calls: list[tuple[str, Any]] = []

    def fake_upgrade(url: str) -> None:
        calls.append(("migrate", url))

    def fake_run(*args: Any, **kwargs: Any) -> None:
        calls.append(("uvicorn", (args, kwargs)))

    monkeypatch.setattr("findash.__main__.upgrade_database", fake_upgrade)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv(
        "FINDASH_INVESTMENTS_DATABASE_URL", "sqlite:///configured.db"
    )
    return calls


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_lists_health_endpoint(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]


def test_docs_page_is_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_creating_the_app_does_not_open_the_database(
    settings: Settings, database_path: Path
) -> None:
    create_app(settings)

    assert not database_path.parent.exists()


def test_requests_get_a_session_while_the_app_runs(
    settings: Settings, database_path: Path
) -> None:
    app = create_app(settings)

    @app.get("/test/session")
    def use_session(session: InvestmentsSession) -> dict[str, int]:
        return {"value": session.scalar(text("SELECT 1")) or 0}

    with TestClient(app) as client:
        response = client.get("/test/session")
        assert response.json() == {"value": 1}
        assert app.state.investments_session_factory is not None

    assert database_path.exists()


@pytest.mark.parametrize(
    ("argv", "host", "port"),
    [
        ([], "127.0.0.1", 8000),
        (["--host", "0.0.0.0", "--port", "8765"], "0.0.0.0", 8765),
    ],
)
def test_start_command_migrates_then_runs_uvicorn(
    start_calls: list[tuple[str, Any]], argv: list[str], host: str, port: int
) -> None:
    main(argv)

    assert start_calls == [
        ("migrate", "sqlite:///configured.db"),
        (
            "uvicorn",
            (
                ("findash.main:create_app",),
                {"factory": True, "host": host, "port": port},
            ),
        ),
    ]


def test_start_command_stops_when_migration_fails(
    start_calls: list[tuple[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_upgrade(url: str) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("findash.__main__.upgrade_database", failing_upgrade)

    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 1
    assert "database migration failed: disk full" in capsys.readouterr().err
    assert start_calls == []
