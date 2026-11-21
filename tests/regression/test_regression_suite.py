"""Tier 4 Regression Tests: Idempotency caching, state immutability, and multi-cycle execution."""

from __future__ import annotations

import datetime
from contracts.schemas import (
    NextTaskAssignmentRequest,
    PriorityLevel,
    TaskSpec,
    TaskState,
    ReviewSubmissionPayload,
    EvaluationSubmissionPayload,
    EvaluationVerdict,
    SchemaVersion,
)
from src.enterprise_core.service import EnterpriseCoreService


def test_idempotent_next_task_assignment(sample_task_spec: TaskSpec) -> None:
    """Verify submitting duplicate assignment requests with identical idempotency_key returns cached response."""
    service = EnterpriseCoreService()
    task = service.create_task(sample_task_spec, actor_id="usr_admin")

    # Move to EVALUATION_PASS
    sub = ReviewSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id="sub_idemp_01",
        task_id=task.task_id,
        candidate_id="cand_01",
        commit_hash="1122334455667788",
        repository_url="https://github.com/test/repo",
        review_packet_hash="c" * 64,
    )
    task = service.submit_review(sub, expected_version=1, actor_id="cand_01")
    task = service.start_review(task.task_id, expected_version=2, reviewer_id="rev_01")
    eval_payload = EvaluationSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id=sub.submission_id,
        reviewer_id="rev_01",
        verdict=EvaluationVerdict.PASS,
        score=92,
        findings="Passed regression audit.",
        signature="reviewer_sig_pass_12345",
    )
    task = service.evaluate_submission(eval_payload, expected_version=3, actor_id="rev_01")

    # First assignment call
    assign_req = NextTaskAssignmentRequest(
        schema_version=SchemaVersion.V1_0,
        submission_id=sub.submission_id,
        reviewer_id="rev_01",
        next_task_id="T-GOV-003",
        assignee_candidate_id="cand_01",
        target_date=datetime.date(2026, 11, 28),
        priority=PriorityLevel.HIGH,
        idempotency_key="idempotency_token_unique_9999",
    )

    resp1 = service.assign_next_task(assign_req, expected_version=4, actor_id="rev_01")
    
    # Second duplicate assignment call with same idempotency key (even with same or different version argument)
    resp2 = service.assign_next_task(assign_req, expected_version=4, actor_id="rev_01")

    assert resp1.assignment_id == resp2.assignment_id
    assert resp1.gov_os_tx_hash == resp2.gov_os_tx_hash
    # Only 1 assignment event recorded in ledger
    assert service.ledger.event_count == 5
