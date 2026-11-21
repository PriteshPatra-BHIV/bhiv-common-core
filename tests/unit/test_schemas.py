"""Tier 1 Unit Tests: Schema validation and boundary constraints."""

from __future__ import annotations

import datetime
import pytest
from pydantic import ValidationError

from contracts.schemas import (
    DifficultyLevel,
    EvaluationSubmissionPayload,
    EvaluationVerdict,
    PriorityLevel,
    ReviewSubmissionPayload,
    TaskSpec,
    UserRole,
    SchemaVersion,
)


def test_task_spec_valid(sample_task_spec: TaskSpec) -> None:
    """Verify standard TaskSpec compiles and validates successfully."""
    assert sample_task_spec.task_id == "T-GOV-002"
    assert sample_task_spec.schema_version == SchemaVersion.V1_0
    assert len(sample_task_spec.phases) == 7
    assert len(sample_task_spec.acceptance_criteria) == 7


def test_task_spec_invalid_id_format() -> None:
    """Verify task_id regex rejection for invalid formats."""
    with pytest.raises(ValidationError):
        TaskSpec(
            schema_version=SchemaVersion.V1_0,
            task_id="INVALID_ID_WITHOUT_PREFIX",
            title="Test Task Title",
            canonical_spec_body="A valid specification body of sufficient length.",
        )


def test_evaluation_score_bounds() -> None:
    """Verify evaluation score bounds [0, 100]."""
    # Score > 100 must fail
    with pytest.raises(ValidationError):
        EvaluationSubmissionPayload(
            schema_version=SchemaVersion.V1_0,
            submission_id="sub_test_001",
            reviewer_id="rev_01",
            verdict=EvaluationVerdict.PASS,
            score=105,
            findings="Exceeds score limit test",
            signature="valid_cryptographic_signature_here",
        )

    # Score < 0 must fail
    with pytest.raises(ValidationError):
        EvaluationSubmissionPayload(
            schema_version=SchemaVersion.V1_0,
            submission_id="sub_test_001",
            reviewer_id="rev_01",
            verdict=EvaluationVerdict.FAIL,
            score=-5,
            findings="Negative score test",
            signature="valid_cryptographic_signature_here",
        )


def test_review_submission_hash_length() -> None:
    """Verify review_packet_hash requires exactly 64 hexadecimal characters."""
    with pytest.raises(ValidationError):
        ReviewSubmissionPayload(
            schema_version=SchemaVersion.V1_0,
            submission_id="sub_test_001",
            task_id="T-GOV-002",
            candidate_id="cand_01",
            commit_hash="a1b2c3d4",
            repository_url="https://github.com/bhiv/test",
            review_packet_hash="too_short_hash",
        )
