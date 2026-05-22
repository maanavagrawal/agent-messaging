from __future__ import annotations

import asyncio
import json
import time
from threading import Event
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from conftest import auth_headers, entry_payload, start_session
from fixlog.db.models import Account, Base, Verification, VerificationResult, VerifierKind
from fixlog.db.seed import token_hash
from fixlog.db.session import create_fixlog_engine, get_db
from fixlog.main import create_app
from fixlog.sandbox.result import SandboxResult
from fixlog.sandbox.spec import SandboxSpec
from fixlog.workers.verifier import VerifierWorker, apply_unified_diff


class FakeRunner:
    def __init__(self, results: list[SandboxResult]) -> None:
        self.results = results
        self.calls: list[tuple[SandboxSpec, str]] = []

    def run(
        self,
        spec: SandboxSpec,
        workspace: bytes | None,
        command: str,
        timeout_s: int = 60,
        memory_mb: int = 512,
        allow_network: bool = False,
    ) -> SandboxResult:
        self.calls.append((spec, command))
        return self.results.pop(0)


class RaisingRunner:
    def run(
        self,
        spec: SandboxSpec,
        workspace: bytes | None,
        command: str,
        timeout_s: int = 60,
        memory_mb: int = 512,
        allow_network: bool = False,
    ) -> SandboxResult:
        raise RuntimeError("docker unavailable")


class BlockingRunner:
    def __init__(self) -> None:
        self.release = Event()

    def run(
        self,
        spec: SandboxSpec,
        workspace: bytes | None,
        command: str,
        timeout_s: int = 60,
        memory_mb: int = 512,
        allow_network: bool = False,
    ) -> SandboxResult:
        self.release.wait(timeout=5)
        return success()


def success() -> SandboxResult:
    return SandboxResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_ms=1,
        timed_out=False,
        oom_killed=False,
        image_pulled=False,
    )


def failure(stderr: str = "NameError: name 'undefined_variable' is not defined") -> SandboxResult:
    return SandboxResult(
        exit_code=1,
        stdout="",
        stderr=stderr,
        duration_ms=1,
        timed_out=False,
        oom_killed=False,
        image_pulled=False,
    )


def session_factory_for(db_session: Session):
    class Context:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(self, *_args: object) -> None:
            return None

    return Context


def python_entry_payload() -> dict[str, object]:
    payload = entry_payload("NameError: name 'undefined_variable' is not defined")
    payload.update(
        {
            "fix_diff": (
                "--- a/bug.py\n"
                "+++ b/bug.py\n"
                "@@ -1 +1,2 @@\n"
                "+undefined_variable = 'fixed'\n"
                " print(undefined_variable)\n"
            ),
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
        }
    )
    return payload


def test_apply_unified_diff_updates_file() -> None:
    files = {"bug.py": "print(undefined_variable)\n"}
    fixed = apply_unified_diff(
        files,
        (
            "--- a/bug.py\n"
            "+++ b/bug.py\n"
            "@@ -1 +1,2 @@\n"
            "+undefined_variable = 'fixed'\n"
            " print(undefined_variable)\n"
        ),
    )

    assert fixed["bug.py"] == "undefined_variable = 'fixed'\nprint(undefined_variable)\n"


def test_apply_unified_diff_reconstructs_missing_original_file() -> None:
    fixed = apply_unified_diff(
        {},
        (
            "--- a/bug.py\n"
            "+++ b/bug.py\n"
            "@@ -1 +1,2 @@\n"
            "+x = 42\n"
            " print(x)\n"
        ),
    )

    assert fixed["bug.py"] == "x = 42\nprint(x)\n"


def test_apply_unified_diff_deletes_file() -> None:
    fixed = apply_unified_diff(
        {"old.py": "print('remove me')\n", "keep.py": "print('keep')\n"},
        (
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-print('remove me')\n"
        ),
    )

    assert fixed == {"keep.py": "print('keep')\n"}


def test_verifier_worker_writes_pass_verification(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=python_entry_payload(),
    )
    assert create_response.status_code == 201
    entry_id = UUID(create_response.json()["id"])
    runner = FakeRunner([failure(), success()])
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=runner,
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(entry_id)

    assert verification.verifier_kind == VerifierKind.AUTO_SANDBOX
    assert verification.result == VerificationResult.PASS
    assert runner.calls[1][0].files["bug.py"] == "print(undefined_variable)\n"
    assert "base64 -d > /workspace/bug.py" in runner.calls[1][0].setup_commands[-1]


def test_verifier_worker_applies_fix_after_setup_commands(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    payload = entry_payload("NameError: name 'x' is not defined")
    payload.update(
        {
            "fix_diff": (
                "--- a/bug.py\n"
                "+++ b/bug.py\n"
                "@@ -1 +1,2 @@\n"
                "+x = 42\n"
                " print(x)\n"
            ),
            "reproduction_setup": "echo 'print(x)' > bug.py",
            "reproduction_trigger": "python bug.py",
            "reproduction_verify": "python bug.py",
            "sandbox_kind": "docker",
            "sandbox_spec": "python:3.11-slim",
        }
    )
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=payload,
    )
    assert create_response.status_code == 201
    runner = FakeRunner([failure("NameError: name 'x' is not defined"), success()])
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=runner,
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(UUID(create_response.json()["id"]))

    assert verification.result == VerificationResult.PASS
    verify_spec = runner.calls[1][0]
    assert verify_spec.files == {}
    assert verify_spec.setup_commands[0] == "echo 'print(x)' > bug.py"
    assert "base64 -d > /workspace/bug.py" in verify_spec.setup_commands[1]


def test_verifier_worker_fails_when_verify_still_fails(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=python_entry_payload(),
    )
    assert create_response.status_code == 201
    runner = FakeRunner([failure(), failure("NameError: still broken")])
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=runner,
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(UUID(create_response.json()["id"]))

    assert verification.result == VerificationResult.FAIL
    assert "verify: exit_code=1" in (verification.notes or "")
    assert "still broken" in (verification.notes or "")


def test_verifier_worker_records_partial_for_none_sandbox_kind(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    payload = python_entry_payload()
    payload["sandbox_kind"] = "none"
    payload["sandbox_spec"] = "none"
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=payload,
    )
    assert create_response.status_code == 201
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=FakeRunner([]),
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(UUID(create_response.json()["id"]))

    assert verification.result == VerificationResult.PARTIAL
    assert "cannot auto-verify" in (verification.notes or "")


def test_verifier_worker_loop_processes_enqueued_job(tmp_path: Path) -> None:
    db_path = tmp_path / "worker-loop.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        db.add(Account(api_token_hash=token_hash("token-one"), human_name="Ada"))
        db.commit()
    app = create_app(seed_accounts=False, start_verifier=False)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    worker = VerifierWorker(
        session_factory=SessionLocal,
        runner=FakeRunner([failure(), success()]),
        allowed_images={"python:3.11-slim"},
    )
    with TestClient(app) as client:
        session = start_session(client)
        create_response = client.post(
            "/entries",
            headers=auth_headers(session_id=session["session_id"]),
            json=python_entry_payload(),
        )
        assert create_response.status_code == 201
        entry_id = UUID(create_response.json()["id"])

    async def run_worker() -> None:
        await worker.start()
        assert await worker.enqueue(entry_id) is True
        await asyncio.wait_for(worker.queue.join(), timeout=2)
        await worker.stop()

    asyncio.run(run_worker())

    with SessionLocal() as db:
        verification = db.scalar(select(Verification))
        assert verification is not None
        assert verification.result == VerificationResult.PASS
    assert worker.status()["running"] is False
    assert worker.result_counts["pass"] == 1


def test_verifier_worker_stop_does_not_hang_on_active_job(tmp_path: Path) -> None:
    db_path = tmp_path / "worker-stop.sqlite3"
    engine = create_fixlog_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        db.add(Account(api_token_hash=token_hash("token-one"), human_name="Ada"))
        db.commit()
    app = create_app(seed_accounts=False, start_verifier=False)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    runner = BlockingRunner()
    worker = VerifierWorker(
        session_factory=SessionLocal,
        runner=runner,
        allowed_images={"python:3.11-slim"},
        shutdown_timeout_s=0,
    )
    with TestClient(app) as client:
        session = start_session(client)
        create_response = client.post(
            "/entries",
            headers=auth_headers(session_id=session["session_id"]),
            json=python_entry_payload(),
        )
        assert create_response.status_code == 201
        entry_id = UUID(create_response.json()["id"])

    async def run_worker() -> float:
        await worker.start()
        assert await worker.enqueue(entry_id) is True
        await asyncio.sleep(0.05)
        started = time.monotonic()
        await worker.stop()
        return time.monotonic() - started

    duration = asyncio.run(run_worker())
    runner.release.set()

    assert duration < 1
    assert worker.status()["running"] is False
    assert worker.last_error == "verifier worker shutdown timed out"


def test_verifier_worker_fails_when_image_not_whitelisted(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    payload = python_entry_payload()
    payload["sandbox_spec"] = json.dumps(
        {"base_image": "python:latest", "files": {"bug.py": "print('x')\n"}}
    )
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=payload,
    )
    assert create_response.status_code == 201
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=FakeRunner([]),
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(UUID(create_response.json()["id"]))

    assert verification.result == VerificationResult.FAIL
    assert "image not in whitelist" in (verification.notes or "")


def test_verifier_worker_writes_partial_when_runner_fails(
    client: TestClient, db_session: Session
) -> None:
    session = start_session(client)
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=python_entry_payload(),
    )
    assert create_response.status_code == 201
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=RaisingRunner(),
        allowed_images={"python:3.11-slim"},
    )

    verification = worker.verify_entry(UUID(create_response.json()["id"]))

    assert verification.result == VerificationResult.PARTIAL
    assert "docker unavailable" in (verification.notes or "")


def test_verifier_worker_queue_overflow(client: TestClient, db_session: Session) -> None:
    session = start_session(client)
    create_response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=python_entry_payload(),
    )
    assert create_response.status_code == 201
    entry_id = UUID(create_response.json()["id"])
    worker = VerifierWorker(
        session_factory=session_factory_for(db_session),
        runner=FakeRunner([]),
        allowed_images={"python:3.11-slim"},
        queue_size=1,
    )

    async def fill_queue() -> tuple[bool, bool]:
        first = await worker.enqueue(entry_id)
        second = await worker.enqueue(entry_id)
        return first, second

    assert asyncio.run(fill_queue()) == (True, False)
    verification = worker.write_queue_overflow(entry_id)

    assert verification.result == VerificationResult.PARTIAL
    assert verification.notes == "queue overflow"
    db_verification = db_session.scalar(select(Verification))
    assert db_verification is not None
