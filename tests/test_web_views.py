from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import (
    auth_headers,
    create_entry,
    create_question,
    entry_payload,
    start_session,
)


def test_feed_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"])
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Agent broadcasts and field notes." in response.text
    assert "Field note" in response.text


def test_feed_page_renders_question_card_and_open_count(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])

    response = client.get("/", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert f"/questions/{question['id']}" in response.text
    assert "Open broadcast" in response.text
    assert "No linked fix yet" in response.text
    assert "Open broadcasts" in response.text
    assert "<dd>1</dd>" in response.text


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
    assert "Field note" in response.text
    assert "Verification pending" in response.text


def test_entry_detail_page_shows_failed_auto_sandbox_notes(
    client: TestClient,
) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    verification = client.post(
        f"/entries/{entry['id']}/verifications",
        headers=auth_headers(),
        json={
            "verifier_kind": "auto_sandbox",
            "result": "fail",
            "env_snapshot": entry["env_context"],
            "notes": "verify: exit_code=1\nstderr:\nstill broken",
        },
    )
    assert verification.status_code == 201

    response = client.get(f"/entries/{entry['id']}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Auto-sandbox verification did not pass." in response.text
    assert "still broken" in response.text
    assert "Verified field note" not in response.text


def test_question_detail_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])
    response = client.get(f"/questions/{question['id']}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "What the agent tried" in response.text
    assert "Candidate resolutions" in response.text
    assert "Agent broadcast" in response.text


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
    assert "Active harness sessions and real agent signals." in response.text
    assert "claude_code" in response.text


def test_exact_error_search_page_returns_expected_substrings(client: TestClient) -> None:
    response = client.get("/search/errors", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Exact error search" in response.text
    assert "Search field notes by normalized error." in response.text


def test_exact_error_search_page_renders_matching_entry(client: TestClient) -> None:
    raw_error = """Traceback (most recent call last):
  File "/tmp/app.py", line 7, in run
    raise ValueError("search branch")
ValueError: search branch
"""
    session = start_session(client)
    entry = create_entry(client, session["session_id"], payload=entry_payload(raw_error))
    verified = client.post(
        f"/entries/{entry['id']}/verifications",
        headers=auth_headers(),
        json={
            "verifier_kind": "human_cli",
            "result": "pass",
            "env_snapshot": entry["env_context"],
            "notes": "search result verified",
        },
    )
    assert verified.status_code == 201

    response = client.get(
        "/search/errors",
        params={"error": raw_error},
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "Exact match found" in response.text
    assert f"/entries/{entry['id']}" in response.text
    assert "1 verification event" in response.text
    assert "ValueError search branch" in response.text


def test_exact_error_search_escapes_reflected_query(client: TestClient) -> None:
    response = client.get(
        "/search/errors",
        params={"error": "<script>alert(1)</script>"},
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "No exact match" in response.text
    assert "No field note matches that normalized error yet." in response.text
