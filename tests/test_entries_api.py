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
            "raw_text": "AlternateError: broken",
            "raw_examples": ["AlternateError: broken"],
            "language": "python",
            "framework": None,
        }
    ]
    entry = create_entry(client, session["session_id"], payload)
    assert "AlternateError: broken" in entry["also_matches"][0]["canonical_string"]


def test_create_entry_populates_structured_error_signature_fields(client: TestClient) -> None:
    session = start_session(client)
    raw = """Traceback (most recent call last):
  File "/tmp/app.py", line 42, in load_user
    return users[user_id]
KeyError: 'SessionABC123456789'
"""

    entry = create_entry(client, session["session_id"], entry_payload(raw))
    signature = entry["error_signature"]

    assert signature["exception_type"] == "KeyError"
    assert signature["exception_message"] == "<ID>"
    assert signature["last_frame_module"] == "app"
    assert signature["last_frame_function"] == "load_user"
    assert signature["traceback_shape"] == [["app", "load_user"]]
    assert signature["error_kind"] == "traceback"
    assert signature["was_chained"] is False


def test_create_entry_reuses_existing_normalized_signature(client: TestClient) -> None:
    session = start_session(client)
    first_raw = """Traceback (most recent call last):
  File "/Users/alice/app.py", line 42, in load_user
    return users[user_id]
KeyError: 'SessionABC123456789'
"""
    second_raw = """Traceback (most recent call last):
  File "/home/bob/app.py", line 99, in load_user
    return users[user_id]
KeyError: 'SessionXYZ987654321'
"""

    first = create_entry(client, session["session_id"], entry_payload(first_raw))
    second = create_entry(client, session["session_id"], entry_payload(second_raw))

    assert second["error_signature"]["id"] == first["error_signature"]["id"]


def test_create_entry_rejects_unsupported_language(client: TestClient) -> None:
    session = start_session(client)
    payload = entry_payload("TypeError: broken")
    payload["error_signature"]["language"] = "javascript"  # type: ignore[index]

    response = client.post(
        "/entries",
        headers=auth_headers(session_id=session["session_id"]),
        json=payload,
    )

    assert response.status_code == 400
    assert "Only language='python' is supported" in response.json()["detail"]


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
