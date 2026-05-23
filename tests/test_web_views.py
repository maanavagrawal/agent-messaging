from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import (
    auth_headers,
    create_entry,
    create_question,
    entry_payload,
    start_session,
)
from fixlog.auth.collector import DEVICE_TOKEN_PREFIX
from fixlog.db.models import DeviceToken


def test_feed_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"])
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Fixlog forum." in response.text
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
    assert 'hx-get="/partials/active-sessions"' in response.text
    assert "claude_code" in response.text

    partial = client.get("/partials/active-sessions", headers={"Accept": "text/html"})
    assert partial.status_code == 200
    assert "web-demo" in partial.text


def test_agent_onboarding_page_returns_scrapeable_instruction(
    client: TestClient,
) -> None:
    response = client.get("/agent", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Send your coding agent to Fixlog." in response.text
    assert "Read http://testserver/skill.md and follow the instructions" in response.text
    assert "I'm a Human" not in response.text
    assert "Open agent skill" in response.text
    assert "Sign in for live sessions" in response.text
    assert "The skill is public Markdown" in response.text
    assert "Manual command shape" in response.text


def test_session_events_page_requires_session_auth_for_html(client: TestClient) -> None:
    session = start_session(client)
    event_response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "agent_message",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {"text": "hello from the watcher", "project_slug": "web-demo"},
        },
    )
    assert event_response.status_code == 200

    response = client.get(
        f"/sessions/{session['session_id']}/events/view",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 401


def test_session_events_page_renders_with_session_auth(client: TestClient) -> None:
    session = start_session(client)
    event_response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "agent_message",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {"text": "hello from the watcher", "project_slug": "web-demo"},
        },
    )
    assert event_response.status_code == 200

    response = client.get(
        f"/sessions/{session['session_id']}/events/view",
        headers={
            **auth_headers(session_id=session["session_id"]),
            "Accept": "text/html",
        },
    )

    assert response.status_code == 200
    assert "agent_message" in response.text
    assert "hello from the watcher" in response.text


def test_device_settings_page_requires_dashboard_auth(client: TestClient) -> None:
    response = client.get(
        "/settings/devices",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 401


def test_device_settings_page_explains_first_time_setup(client: TestClient) -> None:
    response = client.get(
        "/settings/devices",
        headers={**auth_headers(), "Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "Connect your coding agent." in response.text
    assert "First-time setup" in response.text
    assert "Create your setup command" in response.text
    assert "Create setup command" in response.text
    assert "Run this inside the repo you want watched" in response.text
    assert "curl -fsSL" in response.text
    assert "Start capture" in response.text
    assert "Use Claude Code in that repo" in response.text
    assert "Device tokens can only submit collector events." in response.text


def test_device_settings_page_creates_token_once(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post(
        "/settings/devices",
        headers={**auth_headers(), "Accept": "text/html"},
        data={"name": "Jason MacBook Pro"},
    )

    assert created.status_code == 200
    assert "Setup command for Jason MacBook Pro." in created.text
    assert "curl -fsSL" in created.text
    assert "/install.sh | bash -s --" in created.text
    assert f"--token {DEVICE_TOKEN_PREFIX}" in created.text
    assert "Add <code>--background</code>" in created.text

    device_token = db_session.scalar(
        select(DeviceToken).where(DeviceToken.name == "Jason MacBook Pro")
    )
    assert device_token is not None
    assert device_token.token_hash not in created.text

    refreshed = client.get(
        "/settings/devices",
        headers={**auth_headers(), "Accept": "text/html"},
    )

    assert refreshed.status_code == 200
    assert "Jason MacBook Pro" in refreshed.text
    assert "This token is shown once." not in refreshed.text
    assert re.search(r"--token flxdt_[A-Za-z0-9_-]{20,}", refreshed.text) is None


def test_device_settings_page_revokes_owned_token(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post(
        "/settings/devices",
        headers={**auth_headers(), "Accept": "text/html"},
        data={"name": "Collector to revoke"},
    )
    assert created.status_code == 200
    device_token = db_session.scalar(
        select(DeviceToken).where(DeviceToken.name == "Collector to revoke")
    )
    assert device_token is not None

    revoked = client.post(
        f"/settings/devices/{device_token.id}/revoke",
        headers={**auth_headers(), "Accept": "text/html"},
    )

    assert revoked.status_code == 200
    assert "Collector to revoke" in revoked.text
    assert "revoked" in revoked.text
    db_session.refresh(device_token)
    assert device_token.revoked_at is not None


def test_device_settings_page_cannot_revoke_other_account_token(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post(
        "/settings/devices",
        headers={**auth_headers("token-one"), "Accept": "text/html"},
        data={"name": "Ada collector"},
    )
    assert created.status_code == 200
    device_token = db_session.scalar(
        select(DeviceToken).where(DeviceToken.name == "Ada collector")
    )
    assert device_token is not None

    response = client.post(
        f"/settings/devices/{device_token.id}/revoke",
        headers={**auth_headers("token-two"), "Accept": "text/html"},
    )

    assert response.status_code == 404


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
