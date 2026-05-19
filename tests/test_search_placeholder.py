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
            "canonical_string": "SecondaryError: missing",
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

