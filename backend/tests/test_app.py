import pytest
from fastapi.testclient import TestClient

from findash import __main__ as entry
from findash.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_lists_health_endpoint(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]


def test_docs_page_is_served(client):
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    ("argv", "host", "port"),
    [
        ([], "127.0.0.1", 8000),
        (["--host", "0.0.0.0", "--port", "8765"], "0.0.0.0", 8765),
    ],
)
def test_start_command_runs_uvicorn(monkeypatch, argv, host, port):
    calls = []
    monkeypatch.setattr(
        entry.uvicorn, "run", lambda *a, **k: calls.append((a, k))
    )

    entry.main(argv)

    assert calls == [(("findash.main:app",), {"host": host, "port": port})]
