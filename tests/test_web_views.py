from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, create_question, start_session


def test_feed_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"])
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "fixlog feed" in response.text
    assert "ENTRY" in response.text


def test_feed_partial_returns_ul_only(client: TestClient) -> None:
    response = client.get("/partials/feed-list", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.text.strip().startswith("<ul")


def test_entry_detail_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    response = client.get(f"/entries/{entry['id']}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Fix diff" in response.text
    assert "Reproduction" in response.text


def test_question_detail_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])
    response = client.get(f"/questions/{question['id']}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Attempts made" in response.text
    assert "Linked entries" in response.text


def test_active_sessions_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    event_response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "tool_result",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {"source_tool": "claude_code", "project_slug": "web-demo"},
        },
    )
    assert event_response.status_code == 200
    response = client.get("/sessions/active", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "active sessions" in response.text
    assert "claude_code" in response.text
