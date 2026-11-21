"""Tier 3 Negative Tests: Security boundary enforcement, unauthorized mutations, and OCC collisions."""

from __future__ import annotations

import pytest
from contracts.schemas import (
    TaskState,
    UserRole,
    ReviewSubmissionPayload,
    SchemaVersion,
)
from src.enterprise_core.models import ConcurrencyError
from src.enterprise_core.service import EnterpriseCoreService
from src.identity_provider.service import (
    HardenedIdentityProvider,
    SecurityAnomalyError,
)


def test_occ_concurrency_conflict_rejection(sample_task_spec) -> None:
    """Verify that submitting with stale expected_version triggers ConcurrencyError."""
    service = EnterpriseCoreService()
    task = service.create_task(sample_task_spec, actor_id="usr_admin")
    assert task.version == 1

    submission = ReviewSubmissionPayload(
        schema_version=SchemaVersion.V1_0,
        submission_id="sub_test_occ",
        task_id=task.task_id,
        candidate_id="cand_1",
        commit_hash="c1c2c3c4",
        repository_url="https://github.com/bhiv/repo",
        review_packet_hash="a" * 64,
    )

    # Provide wrong expected_version=99 instead of 1
    with pytest.raises(ConcurrencyError, match="OCC conflict on Task"):
        service.submit_review(submission, expected_version=99, actor_id="cand_1")


def test_role_privilege_escalation_prevented() -> None:
    """Verify candidate cannot perform reviewer or admin operations."""
    idp = HardenedIdentityProvider()
    candidate_token = idp.issue_token(user_id="usr_cand", role=UserRole.CANDIDATE)

    # Candidate attempting reviewer action must fail
    with pytest.raises(SecurityAnomalyError, match="Unauthorized role"):
        idp.enforce_role(candidate_token, [UserRole.REVIEWER, UserRole.ADMIN])


def test_forged_bearer_token_blocked() -> None:
    """Verify randomly forged token strings are caught and rejected."""
    idp = HardenedIdentityProvider()
    with pytest.raises(SecurityAnomalyError):
        idp.verify_token("bhiv.eyJzdWIiOiAiaGFja2VyIn0.invalid_signature_hex_value")
