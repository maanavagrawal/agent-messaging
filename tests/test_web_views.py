from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import create_entry, create_question, start_session


def test_feed_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"])
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "fixlog feed" in response.text
    assert "ENTRY" in response.text


def test_feed_partial_returns_ul_only(client: TestClient) -> None:
    response = client.get("/partials/feed-list", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.text.strip().startswith("<ul")


def test_entry_detail_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    entry = create_entry(client, session["session_id"])
    response = client.get(f"/entries/{entry['id']}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Fix diff" in response.text
    assert "Reproduction" in response.text


def test_question_detail_page_returns_expected_substrings(client: TestClient) -> None:
    session = start_session(client)
    question = create_question(client, session["session_id"])
    response = client.get(f"/questions/{question['id']}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Attempts made" in response.text
    assert "Linked entries" in response.text
