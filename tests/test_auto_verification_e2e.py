from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from conftest import auth_headers, error_signature, env_context, start_session
from fixlog.db.models import Account, Base
from fixlog.db.seed import token_hash
from fixlog.db.session import create_fixlog_engine, get_db
from fixlog.main import create_app
from fixlog.workers.verifier import VerifierWorker


def docker_available() -> bool:
    try:
        import docker
    except ModuleNotFoundError:
        return False
    try:
        client = docker.from_env()
        client.ping()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="Docker daemon and docker package are required"
)


def test_auto_verification_e2e_passes_with_real_docker(tmp_path: Path) -> None:
    db_path = tmp_path / "auto-verification.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        db.add(Account(api_token_hash=token_hash("token-one"), human_name="Ada"))
        db.commit()
    worker = VerifierWorker(
        session_factory=SessionLocal,
        allowed_images={"python:3.11-slim"},
        timeout_s=30,
        memory_mb=256,
    )
    app = create_app(seed_accounts=False, verifier_worker=worker)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        session = start_session(client)
        response = client.post(
            "/entries",
            headers=auth_headers(session_id=session["session_id"]),
            json={
                "error_signature": error_signature(
                    "NameError: name 'undefined_variable' is not defined"
                ),
                "also_matches": [],
                "env_context": env_context(),
                "diagnosis": "The variable is used before it is defined.",
                "fix_diff": (
                    "--- a/bug.py\n"
                    "+++ b/bug.py\n"
                    "@@ -1 +1,2 @@\n"
                    "+undefined_variable = 'fixed'\n"
                    " print(undefined_variable)\n"
                ),
                "fix_explanation": "Define the variable before printing it.",
                "reproduction_setup": "",
                "reproduction_trigger": "python bug.py",
                "reproduction_verify": "python bug.py",
                "sandbox_kind": "docker",
                "sandbox_spec": json.dumps(
                    {
                        "base_image": "python:3.11-slim",
                        "files": {"bug.py": "print(undefined_variable)\n"},
                    }
                ),
                "tags": ["auto-sandbox"],
            },
        )
        assert response.status_code == 201, response.text
        entry_id = response.json()["id"]
        deadline = time.time() + 30
        verifications = []
        while time.time() < deadline:
            list_response = client.get(f"/entries/{entry_id}/verifications")
            assert list_response.status_code == 200
            verifications = list_response.json()
            if verifications:
                break
            time.sleep(0.5)

        assert verifications
        assert verifications[0]["verifier_kind"] == "auto_sandbox"
        assert verifications[0]["result"] == "pass"


def test_auto_verification_e2e_applies_fix_after_setup_with_real_docker(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "auto-verification-setup.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        db.add(Account(api_token_hash=token_hash("token-one"), human_name="Ada"))
        db.commit()
    worker = VerifierWorker(
        session_factory=SessionLocal,
        allowed_images={"python:3.11-slim"},
        timeout_s=30,
        memory_mb=256,
    )
    app = create_app(seed_accounts=False, verifier_worker=worker)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        session = start_session(client)
        response = client.post(
            "/entries",
            headers=auth_headers(session_id=session["session_id"]),
            json={
                "error_signature": error_signature("NameError: name 'x' is not defined"),
                "also_matches": [],
                "env_context": env_context(),
                "diagnosis": "The variable is used before it is defined.",
                "fix_diff": (
                    "--- a/bug.py\n"
                    "+++ b/bug.py\n"
                    "@@ -1 +1,2 @@\n"
                    "+x = 42\n"
                    " print(x)\n"
                ),
                "fix_explanation": "Define x before printing it.",
                "reproduction_setup": "echo 'print(x)' > bug.py",
                "reproduction_trigger": "python bug.py",
                "reproduction_verify": "python bug.py",
                "sandbox_kind": "docker",
                "sandbox_spec": "python:3.11-slim",
                "tags": ["auto-sandbox"],
            },
        )
        assert response.status_code == 201, response.text
        entry_id = response.json()["id"]
        deadline = time.time() + 30
        verifications = []
        while time.time() < deadline:
            list_response = client.get(f"/entries/{entry_id}/verifications")
            assert list_response.status_code == 200
            verifications = list_response.json()
            if verifications:
                break
            time.sleep(0.5)

        assert verifications
        assert verifications[0]["verifier_kind"] == "auto_sandbox"
        assert verifications[0]["result"] == "pass"
