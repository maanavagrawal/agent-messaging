from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import auth_headers
from fixlog.auth.collector import DEVICE_TOKEN_PREFIX


def _bearer(token: str, session_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if session_id is not None:
        headers["X-Fixlog-Session-Id"] = session_id
    return headers


def _create_device_token(client: TestClient, name: str = "Maanav MacBook") -> str:
    response = client.post(
        "/device-tokens",
        headers=auth_headers(),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    assert token.startswith(DEVICE_TOKEN_PREFIX)
    return str(token)


def test_account_can_create_and_list_device_tokens(client: TestClient) -> None:
    token = _create_device_token(client)

    response = client.get("/device-tokens", headers=auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "Maanav MacBook"
    assert "token" not in payload[0]
    assert token not in response.text


def test_device_token_can_start_session_and_post_events(client: TestClient) -> None:
    token = _create_device_token(client)
    status = client.get("/collector/status", headers=_bearer(token))
    assert status.status_code == 200
    assert status.json()["auth_kind"] == "device_token"

    session = client.post(
        "/sessions/start",
        headers=_bearer(token),
        json={"model_name": "claude-code", "harness_name": "fixlog-watch"},
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]

    event = client.post(
        f"/sessions/{session_id}/events",
        headers=_bearer(token, session_id=session_id),
        json={
            "kind": "agent_message",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {"text": "from collector"},
        },
    )

    assert event.status_code == 200


def test_device_token_cannot_call_account_scoped_endpoints(client: TestClient) -> None:
    token = _create_device_token(client)

    response = client.get("/sandbox/status", headers=_bearer(token))

    assert response.status_code == 401


def test_revoked_device_token_is_rejected(client: TestClient) -> None:
    token = _create_device_token(client)
    listed = client.get("/device-tokens", headers=auth_headers()).json()
    device_token_id = listed[0]["id"]
    revoked = client.post(
        f"/device-tokens/{device_token_id}/revoke",
        headers=auth_headers(),
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    response = client.get("/collector/status", headers=_bearer(token))

    assert response.status_code == 401
