from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import create_entry, create_question, start_session


def test_feed_returns_mixed_recent_items(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"])
    create_question(client, session["session_id"])

    response = client.get("/feed")
    assert response.status_code == 200
    kinds = {item["kind"] for item in response.json()["items"]}
    assert kinds == {"entry", "question"}

