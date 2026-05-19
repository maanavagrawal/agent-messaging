from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, start_session


def test_confirm_writes_human_cli_pass(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    response = client.post(
        "/confirm",
        headers=auth_headers(session_id=session["session_id"]),
        json={"entry_id": entry["id"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["verifier_kind"] == "human_cli"
    assert body["result"] == "pass"
    assert body["env_snapshot"] == entry["env_context"]


def test_reject_writes_human_cli_fail(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    response = client.post(
        "/reject",
        headers=auth_headers(session_id=session["session_id"]),
        json={"entry_id": entry["id"], "reason": "Did not work here"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["result"] == "fail"
    assert body["notes"] == "Did not work here"

