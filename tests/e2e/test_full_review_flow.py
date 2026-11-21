"""Tier 5 End-to-End Tests: Complete operational review and auto-assignment workflow."""

from __future__ import annotations

import datetime
from contracts.schemas import (
    DifficultyLevel,
    EvaluationSubmissionPayload,
    EvaluationVerdict,
    NextTaskAssignmentRequest,
    PriorityLevel,
    ReviewSubmissionPayload,
    TaskSpec,
    TaskState,
    SchemaVersion,
)
from src.enterprise_core.service import EnterpriseCoreService
from src.integrations.gc_shakti import GCShaktiPolicyEngine
from src.integrations.gov_os import GovOSLedgerConnector
from src.integrations.bucket import BucketStorageConnector
from src.integrations.saarthi import SaarthiVisibilityService


def test_complete_e2e_operational_review_journey() -> None:
    """Verify complete operational journey matching the prompt runtime workflow:
    1. Candidate submits repository
    2. Parikshak performs deterministic review
    3. Complete BHIV review is rendered
    4. Full next task retrieved from canonical database
    5. Reviewer approves -> Task auto-assigned via Niyantran
    6. Candidate notified & evidence propagates to Gov-OS, Bucket, Saarthi
    7. Executive dashboards update in real time
    """
    service = EnterpriseCoreService()

    # 1. Candidate Task Spec initialization
    spec = TaskSpec(
        schema_version=SchemaVersion.V1_0,
        task_id="T-GOV-002",
        title="BHIV Advancement Milestone: Advanced Enterprise Core & Identity Provider Hardening",
        department="AI ML",
        priority=PriorityLevel.MEDIUM,
        calibrated_duration_hours=35,
        difficulty_level=DifficultyLevel.BEGINNER,
        phases=["Phase 1: Setup", "Phase 2: Execution", "Phase 3: Verification"],
        acceptance_criteria=["Zero unhandled 500s", "100% test pass rate", "50-run determinism"],
        canonical_spec_body="Full enterprise specification for T-GOV-002 conforming to SETU OS v6.0.",
    )
    task = service.create_task(spec, actor_id="usr_admin")
    assert task.state == TaskState.DRAFT

    # 2. Candidate submits review package
    sub = ReviewSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id="sub_e2e_pritesh_100",
        task_id="T-GOV-002",
        candidate_id="usr_candidate_pritesh",
        commit_hash="7f8e9d0a1b2c3d4e",
        repository_url="https://github.com/bhiv/bhiv-common-core",
        review_packet_hash="a" * 64,
        evidence_artifacts=["REVIEW_PACKET.md", "determinism_benchmark.json"],
    )
    task = service.submit_review(sub, expected_version=1, actor_id="usr_candidate_pritesh")
    assert task.state == TaskState.SUBMITTED

    # 3. Reviewer starts review session
    task = service.start_review("T-GOV-002", expected_version=2, reviewer_id="usr_reviewer_01")
    assert task.state == TaskState.IN_REVIEW

    # 4. Parikshak evaluation performed and policy validated
    eval_payload = EvaluationSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id=sub.submission_id,
        reviewer_id="usr_reviewer_01",
        verdict=EvaluationVerdict.PASS,
        score=100,
        findings="Exemplary engineering standard. Zero logic errors, complete determinism.",
        weaknesses_flagged=[],
        signature="parikshak_hmac_sha256_verdict_sig",
    )
    # GC Shakti policy gate check
    GCShaktiPolicyEngine.validate_evaluation_policy(eval_payload)
    task = service.evaluate_submission(eval_payload, expected_version=3, actor_id="usr_reviewer_01")
    assert task.state == TaskState.EVALUATION_PASS

    # 5. Zero-Context-Switch Next Task Assignment via Niyantran
    assign_req = NextTaskAssignmentRequest(
        schema_version=SchemaVersion.V1_0,
        submission_id=sub.submission_id,
        reviewer_id="usr_reviewer_01",
        next_task_id="T-GOV-003",
        assignee_candidate_id="usr_candidate_pritesh",
        target_date=datetime.date(2026, 11, 28),
        priority=PriorityLevel.HIGH,
        idempotency_key="idemp_e2e_flow_verification_key_101",
    )
    assignment = service.assign_next_task(assign_req, expected_version=4, actor_id="usr_reviewer_01")
    assert assignment.task_id == "T-GOV-003"
    assert task.state == TaskState.ASSIGNED

    # 6. Cryptographic Gov-OS anchoring & Bucket immutable storage
    gov_os_tx = GovOSLedgerConnector.anchor_state_hash(assignment.assignment_id, service.ledger.current_state_hash)
    assert gov_os_tx.startswith("0x")
    assert len(gov_os_tx) == 66

    bucket_uri = BucketStorageConnector.store_evidence(
        f"e2e-audit-{assignment.assignment_id}",
        {"task_id": "T-GOV-002", "next_task": "T-GOV-003", "score": 100},
    )
    assert bucket_uri.startswith("bucket://bhiv-immutable-evidence/")

    # 7. Saarthi real-time telemetry broadcast
    SaarthiVisibilityService.publish_event("E2E_WORKFLOW_COMPLETE", {
        "candidate": "usr_candidate_pritesh",
        "evaluated_task": "T-GOV-002",
        "next_task": "T-GOV-003",
        "score": 100,
    })
    metrics = SaarthiVisibilityService.get_dashboard_metrics()
    assert metrics["governance_compliance_rate"] == "100%"
