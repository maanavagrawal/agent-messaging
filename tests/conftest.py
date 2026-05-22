from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from fixlog.db.models import Account, Base
from fixlog.db.seed import token_hash
from fixlog.db.session import create_fixlog_engine, get_db
from fixlog.main import create_app


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    db_path = tmp_path / "test.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def seeded_accounts(db_session: Session) -> dict[str, Account]:
    account_1 = Account(api_token_hash=token_hash("token-one"), human_name="Ada")
    account_2 = Account(api_token_hash=token_hash("token-two"), human_name="Grace")
    db_session.add_all([account_1, account_2])
    db_session.commit()
    return {"token-one": account_1, "token-two": account_2}


@pytest.fixture()
def app(db_session: Session):
    app = create_app(seed_accounts=False, start_verifier=False)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture()
def client(app: Any, seeded_accounts: dict[str, Account]) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(token: str = "token-one", session_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if session_id is not None:
        headers["X-Fixlog-Session-Id"] = session_id
    return headers


def start_session(client: TestClient, token: str = "token-one") -> dict[str, str]:
    response = client.post(
        "/sessions/start",
        headers=auth_headers(token),
        json={"model_name": "claude-sonnet-4-5", "harness_name": "codex"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def env_context() -> dict[str, object]:
    return {
        "language_version": "3.12",
        "framework_version": None,
        "key_deps": {"fastapi": "0.135.3"},
        "os": "darwin",
    }


def error_signature(text: str = "ValueError: broken") -> dict[str, object]:
    return {
        "raw_text": text,
        "raw_examples": [text],
        "language": "python",
        "framework": None,
    }


def entry_payload(text: str = "ValueError: broken") -> dict[str, object]:
    return {
        "error_signature": error_signature(text),
        "also_matches": [],
        "env_context": env_context(),
        "diagnosis": "The value is not initialized.",
        "fix_diff": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-broken\n+fixed\n",
        "fix_explanation": "Initialize the value before use.",
        "reproduction_setup": "python -m venv .venv",
        "reproduction_trigger": "python app.py",
        "reproduction_verify": "pytest",
        "sandbox_kind": "venv",
        "sandbox_spec": "pytest==9.0.3",
        "tags": ["value-error"],
    }


def create_entry(client: TestClient, session_id: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    response = client.post(
        "/entries",
        headers=auth_headers(session_id=session_id),
        json=payload or entry_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def question_payload(text: str = "ValueError: broken") -> dict[str, object]:
    return {
        "error_signature": error_signature(text),
        "env_context": env_context(),
        "attempts_made": ["Tried reinstalling dependencies"],
        "agent_metadata": {
            "model": "claude-sonnet-4-5",
            "harness": "codex",
            "tools_available": ["shell"],
        },
    }


def create_question(client: TestClient, session_id: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    response = client.post(
        "/questions",
        headers=auth_headers(session_id=session_id),
        json=payload or question_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()
