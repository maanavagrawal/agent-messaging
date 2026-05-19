from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, entry_payload, start_session


def test_create_list_and_get_entry(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])

    list_response = client.get("/entries")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == entry["id"]

    detail_response = client.get(
        f"/entries/{entry['id']}", headers={"Accept": "application/json"}
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["diagnosis"] == "The value is not initialized."


def test_create_entry_links_also_matches(client: TestClient) -> None:
    session = start_session(client)
    payload = entry_payload("PrimaryError: broken")
    payload["also_matches"] = [
        {
            "canonical_string": "AlternateError: broken",
            "raw_examples": ["AlternateError: broken"],
            "language": "python",
            "framework": None,
        }
    ]
    entry = create_entry(client, session["session_id"], payload)
    assert entry["also_matches"][0]["canonical_string"] == "AlternateError: broken"


def test_patch_entry_allowed_field_and_records_edit(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])

    response = client.patch(
        f"/entries/{entry['id']}",
        headers=auth_headers(),
        json={
            "field_changed": "diagnosis",
            "new_value": "Updated diagnosis",
            "reason": "Clarify root cause",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["diagnosis"] == "Updated diagnosis"
    assert body["edit_history"][0]["field_changed"] == "diagnosis"


def test_patch_entry_rejects_fix_diff(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])

    response = client.patch(
        f"/entries/{entry['id']}",
        headers=auth_headers(),
        json={
            "field_changed": "fix_diff",
            "new_value": "new diff",
            "reason": "Try to mutate immutable diff",
        },
    )
    assert response.status_code == 400
    assert "superseding entry" in response.json()["detail"]


def test_supersede_entry_records_edit(client: TestClient) -> None:
    session = start_session(client)
    old_entry = create_entry(client, session["session_id"], entry_payload("Error: old"))
    new_entry = create_entry(client, session["session_id"], entry_payload("Error: new"))

    response = client.post(
        f"/entries/{old_entry['id']}/supersede",
        headers=auth_headers(),
        json={"new_entry_id": new_entry["id"], "reason": "Better reproduction"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["superseded_by"] == new_entry["id"]
    assert body["edit_history"][0]["field_changed"] == "superseded_by"

