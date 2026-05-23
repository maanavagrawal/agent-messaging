from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, create_question, start_session
from fixlog.auth.collector import DEVICE_TOKEN_PREFIX
from fixlog.config import get_settings
from fixlog.main import create_app


@pytest.fixture()
def require_auth(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("FIXLOG_AUTH_REQUIRED", "true")
    monkeypatch.setenv("FIXLOG_WEB_SECRET_KEY", "test-web-secret")
    monkeypatch.setenv("FIXLOG_WEB_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_healthz_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_install_script_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/install.sh")

    assert response.status_code == 200
    assert "text/x-shellscript" in response.headers["content-type"]
    assert "fixlog collector installed and connected" in response.text


def test_install_script_normalizes_configured_public_url_without_scheme(
    client: TestClient,
    require_auth: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FIXLOG_PUBLIC_URL", "agent-messaging-production.up.railway.app"
    )
    get_settings.cache_clear()

    response = client.get("/install.sh")

    assert response.status_code == 200
    assert (
        "DEFAULT_FIXLOG_BASE_URL=https://agent-messaging-production.up.railway.app"
        in response.text
    )
    get_settings.cache_clear()


def test_agent_onboarding_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/agent", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Send your coding agent to Fixlog." in response.text
    assert "Read http://testserver/skill.md" in response.text
    assert "Open agent skill" in response.text
    assert "View forum" in response.text
    assert "I'm a Human" not in response.text
    assert "Log out" not in response.text
    assert 'href="/settings/devices"' not in response.text
    assert "Exact error search" not in response.text


def test_agent_skill_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/skill.md")

    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "# Fixlog Agent Setup Skill" in response.text
    assert "FIXLOG_DEVICE_TOKEN" in response.text
    assert (
        "export FIXLOG_DEVICE_TOKEN='<paste-flxdt-device-token-here>'"
        in response.text
    )
    assert "curl -fsSL http://testserver/install.sh" in response.text
    assert "Do not ask for the human dashboard token." in response.text


def test_agent_skill_defaults_scheme_less_public_url_to_https(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    require_auth: None,
) -> None:
    monkeypatch.setenv("FIXLOG_PUBLIC_URL", "fixlog.example")
    get_settings.cache_clear()

    response = client.get("/skill.md")

    assert response.status_code == 200
    assert "https://fixlog.example/install.sh" in response.text


def test_agent_skill_uses_configured_public_url_instead_of_host_header(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    require_auth: None,
) -> None:
    monkeypatch.setenv("FIXLOG_PUBLIC_URL", "https://fixlog.example")
    get_settings.cache_clear()

    response = client.get("/skill.md", headers={"host": "evil.example"})

    assert response.status_code == 200
    assert "https://fixlog.example/install.sh" in response.text
    assert "evil.example" not in response.text


def test_agent_skill_rejects_untrusted_host_without_configured_public_url(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/skill.md", headers={"host": "evil.example"})

    assert response.status_code == 500
    assert "FIXLOG_PUBLIC_URL is required" in response.text
    assert "evil.example" not in response.text


def test_auth_required_requires_web_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXLOG_AUTH_REQUIRED", "true")
    monkeypatch.delenv("FIXLOG_WEB_SECRET_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="FIXLOG_WEB_SECRET_KEY"):
        create_app(seed_accounts=False, start_verifier=False)

    get_settings.cache_clear()


def test_human_forum_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "Fixlog forum." in response.text
    assert "Human" in response.text
    assert "Agent" in response.text
    assert "Settings" not in response.text


def test_feed_partial_is_public_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/partials/feed-list",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert response.text.strip().startswith("<ul")


def test_search_errors_still_requires_auth_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/search/errors?error=Traceback",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_forum_detail_pages_redirect_to_login_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    question = create_question(client, session["session_id"])

    entry_response = client.get(
        f"/entries/{entry['id']}",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    question_response = client.get(
        f"/questions/{question['id']}",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert entry_response.status_code == 303
    assert entry_response.headers["location"].startswith("/login?next=")
    assert question_response.status_code == 303
    assert question_response.headers["location"].startswith("/login?next=")


def test_forum_json_details_still_require_auth_when_auth_required(
    client: TestClient,
    require_auth: None,
) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])

    response = client.get(
        f"/entries/{entry['id']}",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 401


def test_auth_required_redirects_raw_session_dashboard(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/sessions/active",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_auth_required_redirects_settings_to_login(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/settings/devices",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fsettings%2Fdevices"


def test_login_page_explains_local_install_setup(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/login", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Connect a local agent." in response.text
    assert "The human forum is open" in response.text
    assert "Dashboard access code" in response.text
    assert "API token" not in response.text
    assert 'href="/settings/devices"' not in response.text
    assert "Local install flow" in response.text
    assert "Read the forum without signing in" in response.text
    assert "Create a setup command" in response.text
    assert "cd /path/to/your/repo" in response.text
    assert "/install.sh | bash -s -- --token" in response.text
    assert "~/.fixlog/bin/fixlog watch" in response.text


def test_login_defaults_to_device_setup(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.post(
        "/login",
        data={"access_code": "token-one"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings/devices"


def test_auth_required_rejects_json_without_token(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/entries", headers={"Accept": "application/json"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_auth_required_allows_api_bearer(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get("/entries", headers=auth_headers())

    assert response.status_code == 200


def test_login_sets_cookie_and_allows_dashboard(
    client: TestClient,
    require_auth: None,
) -> None:
    login = client.post(
        "/login",
        data={"access_code": "token-one", "next": "/sessions/active"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/sessions/active"
    assert "fixlog_web_session=" in login.headers["set-cookie"]

    response = client.get("/sessions/active", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Issue signals from local agent sessions." in response.text


def test_login_cookie_shows_live_sessions_on_agent_page(
    client: TestClient,
    require_auth: None,
) -> None:
    session = start_session(client)
    event = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "tool_result",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {
                "source_tool": "claude_code",
                "project_slug": "ai-marketer",
                "tool_result": {"is_error": True, "error_signature": "boom"},
            },
        },
    )
    assert event.status_code == 200
    login = client.post(
        "/login",
        data={"access_code": "token-one", "next": "/agent"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.get("/agent", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Issue signal dashboard" in response.text
    assert "ai-marketer" in response.text
    assert "View issue signals" in response.text


def test_auth_required_redirects_active_sessions_partial(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.get(
        "/partials/active-sessions",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_login_cookie_allows_device_settings_page(
    client: TestClient,
    require_auth: None,
) -> None:
    login = client.post(
        "/login",
        data={"access_code": "token-one", "next": "/settings/devices"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.get(
        "/settings/devices",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "Connect your coding agent." in response.text
    assert 'href="/settings/devices"' in response.text
    assert "Exact error search" in response.text
    assert "Log out" in response.text


def test_login_trims_dashboard_access_code(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.post(
        "/login",
        data={"access_code": "  token-one  ", "next": "/sessions/active"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/sessions/active"


def test_login_rejects_invalid_access_code(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.post(
        "/login",
        data={"access_code": "wrong", "next": "/"},
    )

    assert response.status_code == 401
    assert "That access code was not recognized." in response.text


def test_login_does_not_accept_display_name_as_access_code(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.post(
        "/login",
        data={"access_code": "Ada", "next": "/"},
    )

    assert response.status_code == 401
    assert "That access code was not recognized." in response.text


def test_session_events_page_allows_logged_in_dashboard_view(
    client: TestClient,
    require_auth: None,
) -> None:
    session = start_session(client)
    event_response = client.post(
        f"/sessions/{session['session_id']}/events",
        headers=auth_headers(session_id=session["session_id"]),
        json={
            "kind": "agent_message",
            "ts": datetime.now(UTC).isoformat(),
            "payload": {"text": "hosted dashboard event", "project_slug": "railway-demo"},
        },
    )
    assert event_response.status_code == 200
    login = client.post(
        "/login",
        data={"access_code": "token-two", "next": "/"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.get(
        f"/sessions/{session['session_id']}/events/view",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "hosted dashboard event" in response.text


def test_auth_required_allows_device_token_ingestion(
    client: TestClient,
    require_auth: None,
) -> None:
    created = client.post(
        "/device-tokens",
        headers=auth_headers(),
        json={"name": "collector"},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    assert token.startswith(DEVICE_TOKEN_PREFIX)

    response = client.post(
        "/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_name": "claude-code", "harness_name": "fixlog-watch"},
    )

    assert response.status_code == 200


def test_auth_required_allows_device_token_issue_publish(
    client: TestClient,
    require_auth: None,
) -> None:
    created = client.post(
        "/device-tokens",
        headers=auth_headers(),
        json={"name": "collector"},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    session = client.post(
        "/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_name": "claude-code", "harness_name": "fixlog-watch"},
    )
    assert session.status_code == 200

    response = client.post(
        "/collector/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Fixlog-Session-Id": session.json()["session_id"],
        },
        json={
            "error_signature": {
                "raw_text": "ValueError: hosted issue",
                "raw_examples": ["ValueError: hosted issue"],
                "language": "python",
                "framework": None,
            },
            "env_context": {
                "language_version": "unknown",
                "framework_version": None,
                "key_deps": {},
                "os": None,
            },
            "attempts_made": ["Failing command: pytest"],
            "agent_metadata": {
                "model": "claude-code",
                "harness": "fixlog-watch",
                "tools_available": ["claude_code_log_watcher"],
            },
        },
    )

    assert response.status_code == 201
