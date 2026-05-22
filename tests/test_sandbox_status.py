from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers


class FakeWorker:
    def status(self) -> dict[str, object]:
        return {
            "running": True,
            "queue_depth": 3,
            "last_error": None,
            "recent_result_counts": {"pass": 2},
        }


def test_sandbox_status_when_worker_disabled(client: TestClient) -> None:
    response = client.get("/sandbox/status", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {
        "running": False,
        "queue_depth": 0,
        "last_error": None,
        "recent_result_counts": {},
    }


def test_sandbox_status_reports_worker_state(client: TestClient) -> None:
    client.app.state.verifier_worker = FakeWorker()

    response = client.get("/sandbox/status", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["running"] is True
    assert response.json()["queue_depth"] == 3


def test_sandbox_status_requires_auth(client: TestClient) -> None:
    response = client.get("/sandbox/status")

    assert response.status_code == 401
