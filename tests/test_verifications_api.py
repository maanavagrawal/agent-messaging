from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, env_context, start_session


def test_create_and_list_verification(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    response = client.post(
        f"/entries/{entry['id']}/verifications",
        headers=auth_headers(),
        json={
            "verifier_kind": "agent_out_of_context",
            "result": "partial",
            "env_snapshot": env_context(),
            "notes": "Verified diagnosis only",
        },
    )
    assert response.status_code == 201
    assert response.json()["result"] == "partial"

    list_response = client.get(f"/entries/{entry['id']}/verifications")
    assert list_response.status_code == 200
    assert list_response.json()[0]["notes"] == "Verified diagnosis only"

