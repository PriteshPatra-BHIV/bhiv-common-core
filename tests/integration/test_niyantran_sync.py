"""Tier 2 Integration Tests: Complete lifecycle and Niyantran sync."""

from __future__ import annotations

import datetime
from contracts.schemas import (
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
from src.integrations.niyantran import NiyantranEngine


def test_core_service_full_pipeline_with_niyantran(sample_task_spec: TaskSpec) -> None:
    """Verify entire programmatic pipeline: create -> submit -> start review -> evaluate -> assign."""
    service = EnterpriseCoreService()

    # Step 1: Create task
    task = service.create_task(sample_task_spec, actor_id="usr_admin")
    assert task.state == TaskState.DRAFT
    assert task.version == 1

    # Step 2: Candidate submits review
    submission = ReviewSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id="sub_test_001",
        task_id=sample_task_spec.task_id,
        candidate_id="usr_candidate_pritesh",
        commit_hash="a1b2c3d4e5f67890",
        repository_url="https://github.com/bhiv/bhiv-common-core",
        review_packet_hash="f" * 64,
        evidence_artifacts=["review_packet.md", "50_run_hashes.json"],
    )
    task = service.submit_review(submission, expected_version=1, actor_id="usr_candidate_pritesh")
    assert task.state == TaskState.SUBMITTED
    assert task.version == 2

    # Step 3: Reviewer starts review
    task = service.start_review(task.task_id, expected_version=2, reviewer_id="usr_reviewer_01")
    assert task.state == TaskState.IN_REVIEW
    assert task.version == 3

    # Step 4: Parikshak evaluation
    evaluation = EvaluationSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id=submission.submission_id,
        reviewer_id="usr_reviewer_01",
        verdict=EvaluationVerdict.PASS,
        score=100,
        findings="Exceptional architecture adhering strictly to SETU OS Architecture v6.0.",
        weaknesses_flagged=[],
        signature="parikshak_sig_ed25519_verified_001",
    )
    task = service.evaluate_submission(evaluation, expected_version=3, actor_id="usr_reviewer_01")
    assert task.state == TaskState.EVALUATION_PASS
    assert task.version == 4

    # Step 5: Niyantran auto-assignment (Zero-Context-Switch)
    assign_req = NextTaskAssignmentRequest(
        schema_version=SchemaVersion.V1_0,
        submission_id=submission.submission_id,
        reviewer_id="usr_reviewer_01",
        next_task_id="T-GOV-003",
        assignee_candidate_id="usr_candidate_pritesh",
        target_date=datetime.date(2026, 11, 28),
        priority=PriorityLevel.HIGH,
        idempotency_key="idemp_unique_key_1234567890",
    )
    assignment = service.assign_next_task(assign_req, expected_version=4, actor_id="usr_reviewer_01")
    assert assignment.task_id == "T-GOV-003"
    assert assignment.candidate_id == "usr_candidate_pritesh"
    assert assignment.canonical_depth_verified is True
    assert assignment.sync_status == "SYNCHRONIZED"

    # Verify task state is now ASSIGNED and version is 5
    assert task.state == TaskState.ASSIGNED
    assert task.version == 5

    # Verify cryptographic replay ledger
    is_valid, final_hash = service.ledger.replay_and_verify()
    assert is_valid is True
    assert service.ledger.event_count == 5


def test_niyantran_canonical_depth_validation() -> None:
    """Verify Niyantran rejects placeholder task IDs and incomplete specifications."""
    assert NiyantranEngine.verify_canonical_depth("T-GOV-003") is True
    assert NiyantranEngine.verify_canonical_depth("T-GOV-004") is True
    # Rejects placeholder task
    assert NiyantranEngine.verify_canonical_depth("T-placeholder-999") is False
    assert NiyantranEngine.verify_canonical_depth("NON_EXISTENT_TASK") is False
