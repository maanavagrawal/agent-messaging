from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers
from fixlog.auth.collector import DEVICE_TOKEN_PREFIX


def _device_token(client: TestClient) -> str:
    response = client.post(
        "/device-tokens",
        headers=auth_headers(),
        json={"name": "collector"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    assert token.startswith(DEVICE_TOKEN_PREFIX)
    return str(token)


def _collector_session(client: TestClient, token: str) -> str:
    response = client.post(
        "/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model_name": "claude-code",
            "harness_name": "claude-code-log-watcher",
            "source_tool": "claude_code",
            "source_tool_session_id": "native-session",
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["session_id"])


def _issue_payload() -> dict[str, object]:
    raw_error = """Traceback (most recent call last):
  File "/app/scraper.py", line 12, in <module>
    _HEX_COLOR_RE = re.compile("#[0-9a-f]{6}")
NameError: name 're' is not defined
"""
    return {
        "error_signature": {
            "raw_text": raw_error,
            "raw_examples": [raw_error],
            "language": "python",
            "framework": None,
        },
        "env_context": {
            "language_version": "unknown",
            "framework_version": None,
            "key_deps": {},
            "os": None,
        },
        "attempts_made": [
            "Failing command: python -c 'from app import scraper'",
            "Draft diagnosis: scraper.py uses re before importing it.",
            "Project: ai-marketer",
        ],
        "agent_metadata": {
            "model": "claude-code",
            "harness": "claude-code-log-watcher",
            "tools_available": ["claude_code_log_watcher"],
        },
    }


def test_device_token_can_publish_collector_issue_to_human_feed(
    client: TestClient,
) -> None:
    token = _device_token(client)
    session_id = _collector_session(client, token)

    created = client.post(
        "/collector/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Fixlog-Session-Id": session_id,
        },
        json=_issue_payload(),
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["error_signature"]["exception_type"] == "NameError"
    assert body["attempts_made"][0].startswith("Failing command:")

    feed = client.get("/", headers={"Accept": "text/html"})
    assert feed.status_code == 200
    assert "Open broadcast" in feed.text
    assert "NameError" in feed.text


def test_collector_issue_publish_deduplicates_by_session_and_signature(
    client: TestClient,
) -> None:
    token = _device_token(client)
    session_id = _collector_session(client, token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Fixlog-Session-Id": session_id,
    }

    first = client.post("/collector/issues", headers=headers, json=_issue_payload())
    second = client.post("/collector/issues", headers=headers, json=_issue_payload())
    listed = client.get("/questions")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert len(listed.json()["items"]) == 1
