from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import create_entry, entry_payload, start_session


def test_search_exact_hash_finds_canonical_entry(client: TestClient) -> None:
    session = start_session(client)
    create_entry(client, session["session_id"], entry_payload("LookupError: missing"))

    response = client.get("/search", params={"error": "LookupError: missing"})
    assert response.status_code == 200
    body = response.json()
    assert body["exact_match"] is True
    assert len(body["entries"]) == 1


def test_search_exact_hash_finds_also_match_entry(client: TestClient) -> None:
    session = start_session(client)
    payload = entry_payload("PrimaryError: missing")
    payload["also_matches"] = [
        {
            "raw_text": "SecondaryError: missing",
            "raw_examples": ["SecondaryError: missing"],
            "language": "python",
            "framework": None,
        }
    ]
    create_entry(client, session["session_id"], payload)

    response = client.get("/search", params={"error": "SecondaryError: missing"})
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 1


def test_search_missing_signature_returns_empty(client: TestClient) -> None:
    response = client.get("/search", params={"error": "NotFound: none"})
    assert response.status_code == 200
    assert response.json() == {"entries": [], "exact_match": False}


def test_search_normalizes_raw_error_text_to_existing_signature(client: TestClient) -> None:
    session = start_session(client)
    raw = """Traceback (most recent call last):
  File "/tmp/app.py", line 42, in load_user
    return users[user_id]
KeyError: 'SessionABC123456789'
"""
    variation = raw.replace("/tmp/app.py", "/home/other/app.py").replace(
        "line 42", "line 99"
    ).replace("SessionABC123456789", "SessionXYZ987654321")
    create_entry(client, session["session_id"], entry_payload(raw))

    response = client.get("/search", params={"error": variation})

    assert response.status_code == 200
    body = response.json()
    assert body["exact_match"] is True
    assert len(body["entries"]) == 1
