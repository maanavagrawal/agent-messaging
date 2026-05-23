from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import auth_headers, start_session
from fixlog.db.models import AgentSession, SessionEvent


def test_start_session_records_optional_source_session(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/sessions/start",
        headers=auth_headers(),
        json={
            "model_name": "claude-code",
            "harness_name": "claude-code-log-watcher",
            "source_tool": "claude_code",
            "source_tool_session_id": "native-session",
        },
    )
    assert response.status_code == 200
    session = db_session.get(AgentSession, UUID(response.json()["session_id"]))
    assert session is not None
    assert session.source_tool == "claude_code"
    assert session.source_tool_session_id == "native-session"


def test_create_and_list_session_events_requires_matching_session_header(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    ts = datetime.now(UTC)
    response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "tool_result",
            "ts": ts.isoformat(),
            "payload": {
                "source_tool": "claude_code",
                "project_slug": "demo",
                "redacted": True,
            },
        },
    )
    assert response.status_code == 200, response.text
    event = db_session.scalar(select(SessionEvent))
    assert event is not None
    assert event.kind == "tool_result"
    assert event.payload["redacted"] is True

    list_response = client.get(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["kind"] == "tool_result"


def test_create_session_event_rejects_missing_session_header(client: TestClient) -> None:
    session = start_session(client)
    response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(),
        json={"kind": "tool_result", "ts": datetime.now(UTC).isoformat(), "payload": {}},
    )
    assert response.status_code == 401


def test_list_session_events_rejects_missing_session_header_for_json(
    client: TestClient,
) -> None:
    session = start_session(client)
    response = client.get(
        f"/sessions/{session['session_id']}/events",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 401


def test_active_sessions_returns_recent_aggregate(client: TestClient) -> None:
    session = start_session(client)
    for index, kind in enumerate(["tool_result", "stuck_emitted"]):
        response = client.post(
            f"/sessions/{session['session_id']}/events",
            headers=auth_headers(session_id=session["session_id"]),
            json={
                "kind": kind,
                "ts": (datetime.now(UTC) - timedelta(seconds=index)).isoformat(),
                "payload": {
                    "source_tool": "claude_code",
                    "project_slug": "active-demo",
                    "tool_result": {
                        "is_error": True,
                        "error_signature": "Traceback: boom",
                    }
                    if index == 0
                    else None,
                },
            },
        )
        assert response.status_code == 200

    response = client.post("/sessions/active")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["project_slug"] == "active-demo"
    assert item["event_count_last_hour"] == 2
    assert item["redaction_count"] == 0
    assert item["stuck_emitted"] is True


def test_active_sessions_hides_normal_collector_activity(
    client: TestClient,
) -> None:
    session = start_session(client)
    for kind, payload in [
        ("agent_message", {"text": "working normally", "project_slug": "quiet-demo"}),
        (
            "tool_result",
            {
                "project_slug": "quiet-demo",
                "tool_result": {"is_error": False, "content": "ok"},
            },
        ),
    ]:
        response = client.post(
            f"/sessions/{session['session_id']}/events",
            headers=auth_headers(session_id=session["session_id"]),
            json={
                "kind": kind,
                "ts": datetime.now(UTC).isoformat(),
                "payload": payload,
            },
        )
        assert response.status_code == 200

    response = client.post("/sessions/active")

    assert response.status_code == 200
    assert response.json()["items"] == []
