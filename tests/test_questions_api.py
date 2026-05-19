from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import auth_headers, create_entry, create_question, question_payload, start_session


def test_create_list_and_get_question(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])

    list_response = client.get("/questions")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == question["id"]

    detail_response = client.get(
        f"/questions/{question['id']}", headers={"Accept": "application/json"}
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["attempts_made"] == ["Tried reinstalling dependencies"]


def test_link_entry_to_question_is_idempotent(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])
    entry = create_entry(client, session["session_id"])

    for _ in range(2):
        response = client.post(
            f"/questions/{question['id']}/link_entry",
            headers=auth_headers(),
            json={"entry_id": entry["id"]},
        )
        assert response.status_code == 200
        assert len(response.json()["linked_entries"]) == 1


def test_question_status_filter(client: TestClient) -> None:
    session = start_session(client)
    create_question(client, session["session_id"])
    response = client.get("/questions?status=open")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_questions_from_different_sessions_share_normalized_signature(
    client: TestClient,
) -> None:
    first_session = start_session(client)
    second_session = start_session(client)
    raw = """Traceback (most recent call last):
  File "/tmp/app.py", line 42, in parse_config
    int(value)
ValueError: invalid literal for int() with base 10: 'ConfigABC123456789'
"""
    variation = raw.replace("/tmp/app.py", "/Users/alice/app.py").replace(
        "line 42", "line 99"
    ).replace("ConfigABC123456789", "ConfigXYZ987654321")

    first = create_question(
        client,
        first_session["session_id"],
        question_payload(raw),
    )
    second = create_question(
        client,
        second_session["session_id"],
        question_payload(variation),
    )

    assert second["error_signature"]["id"] == first["error_signature"]["id"]
    assert first["error_signature"]["exception_type"] == "ValueError"
