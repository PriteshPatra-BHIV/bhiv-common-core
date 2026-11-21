"""Tier 2 Integration Tests: End-to-end integration across Service, IdP, GC Shakti, Niyantran, Gov-OS, Bucket, and Saarthi."""

from __future__ import annotations

import datetime
from fastapi.testclient import TestClient

from contracts.schemas import (
    EvaluationVerdict,
    PriorityLevel,
    TaskSpec,
    TaskState,
    SchemaVersion,
)


def test_full_service_pipeline_integration(
    client: TestClient,
    admin_token: str,
    reviewer_token: str,
    candidate_token: str,
    sample_task_spec: TaskSpec,
) -> None:
    """Verify complete lifecycle progression via HTTP API endpoints."""
    # 1. Admin creates task in DRAFT
    create_resp = client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=sample_task_spec.model_dump(mode="json"),
    )
    assert create_resp.status_code == 200
    task_data = create_resp.json()["data"]
    assert task_data["task_id"] == "T-GOV-002"
    assert task_data["state"] == TaskState.DRAFT.value
    assert task_data["version"] == 1

    # 2. Candidate submits review package
    sub_payload = {
        "schema_version": "1.0",
        "submission_id": "sub_pritesh_001",
        "task_id": "T-GOV-002",
        "candidate_id": "usr_candidate_pritesh",
        "commit_hash": "a1b2c3d4e5f67890",
        "repository_url": "https://github.com/bhiv/enterprise-core",
        "review_packet_hash": "e" * 64,
        "evidence_artifacts": ["tests.log", "benchmark.json", "coverage.xml"],
    }
    submit_resp = client.post(
        "/api/v1/submissions?expected_version=1",
        headers={"Authorization": f"Bearer {candidate_token}"},
        json=sub_payload,
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["data"]["state"] == TaskState.SUBMITTED.value
    assert submit_resp.json()["data"]["version"] == 2

    # 3. Reviewer starts review
    start_resp = client.post(
        f"/api/v1/reviews/start?task_id=T-GOV-002&expected_version=2",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["state"] == TaskState.IN_REVIEW.value
    assert start_resp.json()["data"]["version"] == 3

    # 4. Reviewer evaluates submission
    eval_payload = {
        "schema_version": "1.0",
        "submission_id": "sub_pritesh_001",
        "reviewer_id": "usr_reviewer_test",
        "verdict": EvaluationVerdict.PASS.value,
        "score": 100,
        "findings": "SETU OS Architecture v6.0 fully satisfied. Exemplary government-grade engineering.",
        "weaknesses_flagged": [],
        "signature": "parikshak_sig_ed25519_verified_001",
    }
    eval_resp = client.post(
        "/api/v1/reviews/evaluate?expected_version=3",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json=eval_payload,
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["data"]["state"] == TaskState.EVALUATION_PASS.value
    assert eval_resp.json()["data"]["version"] == 4

    # 5. Reviewer assigns next task via Niyantran (Zero-Context-Switch)
    assign_payload = {
        "schema_version": "1.0",
        "submission_id": "sub_pritesh_001",
        "reviewer_id": "usr_reviewer_test",
        "next_task_id": "T-GOV-003",
        "assignee_candidate_id": "usr_candidate_pritesh",
        "target_date": "2026-11-28",
        "priority": PriorityLevel.HIGH.value,
        "idempotency_key": "idemp_http_api_test_key_001",
    }
    assign_resp = client.post(
        "/api/v1/reviews/assign-next?expected_version=4",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json=assign_payload,
    )
    assert assign_resp.status_code == 200
    assignment_data = assign_resp.json()["data"]
    assert assignment_data["task_id"] == "T-GOV-003"
    assert assignment_data["sync_status"] == "SYNCHRONIZED"

    # 6. Verify ledger state hash endpoint
    hash_resp = client.get(
        "/api/v1/ledger/state-hash",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert hash_resp.status_code == 200
    hash_data = hash_resp.json()["data"]
    assert hash_data["is_valid"] is True
    assert hash_data["event_count"] >= 4

    # 7. Verify Saarthi metrics endpoint
    metrics_resp = client.get(
        "/api/v1/saarthi/metrics",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert metrics_resp.status_code == 200
    assert "governance_compliance_rate" in metrics_resp.json()["data"]

    # 8. Verify pre-flight health endpoints
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "UP"
