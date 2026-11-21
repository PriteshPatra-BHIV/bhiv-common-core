"""Tier 3 Negative Tests: Malformed payloads, boundary conditions, and zero 500 error verification."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_malformed_json_payload_zero_500(client: TestClient, admin_token: str) -> None:
    """Verify malformed JSON payloads return HTTP 422 with RFC-7807 problem details, NOT 500."""
    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"invalid_field": "completely wrong payload"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Schema Validation Failure"
    assert "status" in body
    assert body["status"] == 422
    assert "invalid_params" in body


def test_unauthenticated_request_zero_500(client: TestClient) -> None:
    """Verify requests lacking Authorization header return HTTP 401, NOT 500."""
    response = client.post("/api/v1/tasks", json={})
    assert response.status_code == 401
    assert "Authorization header" in response.json()["detail"]


def test_tampered_token_request_zero_500(client: TestClient, reviewer_token: str) -> None:
    """Verify tampered token returns HTTP 403, NOT 500."""
    tampered = reviewer_token[:-5] + "12345"
    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {tampered}"},
        json={},
    )
    assert response.status_code == 403
    assert "Cryptographic signature mismatch" in response.json()["detail"]
