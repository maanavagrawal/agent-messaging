from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers


def test_missing_bearer_token_is_401(client: TestClient) -> None:
    response = client.post(
        "/sessions/start",
        json={"model_name": "m", "harness_name": "h"},
    )
    assert response.status_code == 401


def test_invalid_bearer_token_is_401(client: TestClient) -> None:
    response = client.post(
        "/sessions/start",
        headers=auth_headers("wrong"),
        json={"model_name": "m", "harness_name": "h"},
    )
    assert response.status_code == 401


def test_valid_bearer_token_allows_session_start(client: TestClient) -> None:
    response = client.post(
        "/sessions/start",
        headers=auth_headers(),
        json={"model_name": "m", "harness_name": "h"},
    )
    assert response.status_code == 200
    assert response.json()["account_reputation"] == 0.0

