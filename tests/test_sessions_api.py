from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers, start_session


def test_start_session_reuses_persona_for_same_setup(client: TestClient) -> None:
    first = start_session(client)
    second = start_session(client)
    assert first["persona_id"] == second["persona_id"]
    assert first["persona_display_name"] == second["persona_display_name"]
    assert first["session_id"] != second["session_id"]


def test_heartbeat_requires_matching_header_session(client: TestClient) -> None:
    session = start_session(client)
    response = client.post(
        f"/sessions/{session['session_id']}/heartbeat",
        headers=auth_headers(session_id=session["session_id"]),
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_heartbeat_rejects_mismatched_url_session(client: TestClient) -> None:
    session = start_session(client)
    other = start_session(client)
    response = client.post(
        f"/sessions/{other['session_id']}/heartbeat",
        headers=auth_headers(session_id=session["session_id"]),
    )
    assert response.status_code == 401
