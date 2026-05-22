from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers, start_session
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


def test_auth_required_requires_web_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXLOG_AUTH_REQUIRED", "true")
    monkeypatch.delenv("FIXLOG_WEB_SECRET_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="FIXLOG_WEB_SECRET_KEY"):
        create_app(seed_accounts=False, start_verifier=False)

    get_settings.cache_clear()


def test_auth_required_redirects_html_dashboard(
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
        data={"token": "token-one", "next": "/sessions/active"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/sessions/active"
    assert "fixlog_web_session=" in login.headers["set-cookie"]

    response = client.get("/sessions/active", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "Active harness sessions and real agent signals." in response.text


def test_login_rejects_invalid_token(
    client: TestClient,
    require_auth: None,
) -> None:
    response = client.post(
        "/login",
        data={"token": "wrong", "next": "/"},
    )

    assert response.status_code == 401
    assert "That token was not accepted." in response.text


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
        data={"token": "token-two", "next": "/"},
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
