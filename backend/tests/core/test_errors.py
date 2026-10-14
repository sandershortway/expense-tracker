import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from findash.core.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    register_error_handlers,
)


def build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundError("thing_not_found", "thing 7 was not found")

    @app.get("/conflict")
    def conflict() -> None:
        raise ConflictError("thing_exists", "thing already exists")

    @app.get("/generic")
    def generic() -> None:
        raise AppError("bad_thing", "something was wrong")

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app())


@pytest.mark.parametrize(
    ("path", "status", "code", "message"),
    [
        ("/missing", 404, "thing_not_found", "thing 7 was not found"),
        ("/conflict", 409, "thing_exists", "thing already exists"),
        ("/generic", 400, "bad_thing", "something was wrong"),
    ],
)
def test_app_errors_use_structured_body(
    client: TestClient, path: str, status: int, code: str, message: str
) -> None:
    response = client.get(path)

    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}


def test_validation_errors_keep_fastapi_shape(client: TestClient) -> None:
    response = client.get("/items/not-a-number")

    assert response.status_code == 422
    assert "detail" in response.json()
    assert "error" not in response.json()
