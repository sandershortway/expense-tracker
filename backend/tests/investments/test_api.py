from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from findash.core.settings import Settings
from findash.main import create_app

URL = "/api/investments/instruments"
NVIDIA = {"isin": "US67066G1040", "ticker": "NVDA", "name": "Nvidia"}
ASML = {
    "isin": "NL0010273215",
    "ticker": "ASML",
    "name": "ASML",
    "legal_name": "ASML Holding N.V.",
}


@pytest.fixture
def settings(engine: Engine, database_url: str) -> Settings:
    return Settings(investments_database_url=database_url)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def create(client: TestClient, **payload: Any) -> dict[str, Any]:
    response = client.post(URL, json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_create_returns_stored_instrument(client: TestClient) -> None:
    response = client.post(URL, json=ASML)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert {k: body[k] for k in ASML} == ASML
    assert response.headers["location"] == f"{URL}/1"
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert datetime.fromisoformat(body["updated_at"]).utcoffset() == (
        timedelta(0)
    )


def test_create_normalises_input(client: TestClient) -> None:
    body = create(
        client,
        isin="  us67066g1040 ",
        ticker=" nvda ",
        name="  Nvidia  ",
        legal_name="   ",
    )

    assert body["isin"] == "US67066G1040"
    assert body["ticker"] == "NVDA"
    assert body["name"] == "Nvidia"
    assert body["legal_name"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {**NVIDIA, "isin": "US67066G1041"},
        {**NVIDIA, "isin": "US67066G104"},
        {**NVIDIA, "isin": "1S67066G1040"},
        {"ticker": "NVDA", "name": "Nvidia"},
        {**NVIDIA, "ticker": "   "},
        {**NVIDIA, "name": ""},
        {**NVIDIA, "ticker": "X" * 33},
        {**NVIDIA, "name": "X" * 201},
        {**NVIDIA, "legal_name": "X" * 301},
        {**NVIDIA, "exchange": "XNAS"},
        {**NVIDIA, "isin": 123},
    ],
)
def test_invalid_input_is_rejected_and_not_stored(
    client: TestClient, payload: dict[str, Any]
) -> None:
    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert "detail" in response.json()
    assert client.get(URL).json() == []


def test_duplicate_isin_returns_conflict(client: TestClient) -> None:
    create(client, **NVIDIA)

    response = client.post(URL, json={**NVIDIA, "ticker": "NVD"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "instrument_exists"
    assert "US67066G1040" in response.json()["error"]["message"]
    assert len(client.get(URL).json()) == 1


def test_list_returns_instruments_in_id_order(client: TestClient) -> None:
    assert client.get(URL).json() == []
    nvidia = create(client, **NVIDIA)
    asml = create(client, **ASML)

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == [nvidia, asml]


def test_get_returns_instrument(client: TestClient) -> None:
    created = create(client, **ASML)

    response = client.get(f"{URL}/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_instrument_returns_not_found(client: TestClient) -> None:
    response = client.get(f"{URL}/999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "instrument_not_found",
            "message": "instrument 999 was not found",
        }
    }


def test_get_with_non_integer_id_is_rejected(client: TestClient) -> None:
    assert client.get(f"{URL}/abc").status_code == 422


def test_data_persists_across_app_instances(settings: Settings) -> None:
    with TestClient(create_app(settings)) as first:
        created = create(first, **NVIDIA)

    with TestClient(create_app(settings)) as second:
        assert second.get(URL).json() == [created]


def test_openapi_documents_instrument_operations(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths[URL]) == {"post", "get"}
    assert set(paths[f"{URL}/{{instrument_id}}"]) == {"get"}
    assert "409" in paths[URL]["post"]["responses"]
    assert "404" in paths[f"{URL}/{{instrument_id}}"]["get"]["responses"]
