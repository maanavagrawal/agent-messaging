from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from conftest import auth_headers
from fixlog.auth.collector import DEVICE_TOKEN_PREFIX
from fixlog.db.models import Account, AgentPersona, Base
from fixlog.db.seed import token_hash
from fixlog.db.session import create_fixlog_engine, get_db
from fixlog.main import create_app


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


def test_device_token_start_session_is_idempotent_for_source_session(
    client: TestClient,
) -> None:
    token = _create_device_token(client)
    payload = {
        "model_name": "claude-code",
        "harness_name": "fixlog-watch",
        "source_tool": "claude_code",
        "source_tool_session_id": "claude-session-one",
    }

    first = client.post("/sessions/start", headers=_bearer(token), json=payload)
    second = client.post("/sessions/start", headers=_bearer(token), json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == first.json()["session_id"]


def test_concurrent_device_token_starts_do_not_500_on_fresh_persona(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "race.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    with SessionLocal() as session:
        session.add(Account(api_token_hash=token_hash("token-one"), human_name="Ada"))
        session.commit()

    app = create_app(seed_accounts=False, start_verifier=False)

    def override_get_db() -> Generator[Session, None, None]:
        with SessionLocal() as session:
            yield session

    @contextmanager
    def auth_session() -> Generator[Session, None, None]:
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = auth_session

    with TestClient(app, raise_server_exceptions=False) as local_client:
        token = _create_device_token(local_client)
        body = {
            "model_name": "claude-code",
            "harness_name": "claude-code-log-watcher",
            "source_tool": "claude_code",
            "source_tool_session_id": "same-source-session",
        }

        def start_once() -> tuple[int, str]:
            response = local_client.post(
                "/sessions/start",
                headers=_bearer(token),
                json=body,
            )
            return response.status_code, response.text

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = [
                future.result()
                for future in as_completed(
                    [executor.submit(start_once) for _ in range(20)]
                )
            ]

    assert [status for status, _text in results] == [200] * 20
    with SessionLocal() as session:
        personas = session.scalars(select(AgentPersona)).all()
    assert len(personas) == 1


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
