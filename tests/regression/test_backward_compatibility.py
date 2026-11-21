"""Tier 4 Regression Tests: Legacy schema ingestion and backward compatibility."""

from __future__ import annotations

from contracts.schemas import SchemaVersion, PriorityLevel, DifficultyLevel
from src.enterprise_core.adapters import LegacyPayloadAdapter


def test_legacy_payload_adapter_task_spec() -> None:
    """Verify legacy v0.8/v0.9 task payload is safely normalized to v1.0 TaskSpec."""
    legacy_payload = {
        "id": "GOV-001",
        "name": "Legacy Enterprise Core Setup",
        "dept": "AI ML",
        "priority": "HIGH",
        "difficulty": "BEGINNER",
        "duration": 40,
        "phases": ["Phase 1", "Phase 2"],
        "criteria": ["Criterion 1"],
        "body": "Legacy task specification description with adequate character length for validation.",
    }

    adapted = LegacyPayloadAdapter.adapt_task_spec(legacy_payload)
    assert adapted.schema_version == SchemaVersion.V1_0
    assert adapted.task_id == "T-GOV-001"
    assert adapted.title == "Legacy Enterprise Core Setup"
    assert adapted.priority == PriorityLevel.HIGH
    assert adapted.difficulty_level == DifficultyLevel.BEGINNER
    assert adapted.calibrated_duration_hours == 40


def test_legacy_payload_adapter_submission() -> None:
    """Verify legacy review submission format is mapped to v1.0 ReviewSubmissionPayload."""
    legacy_submission = {
        "sub_id": "sub_old_99",
        "task_id": "GOV-001",
        "author": "pritesh_patra",
        "commit": "deadbeef12345678",
        "repo_url": "https://github.com/bhiv/old-repo",
        "packet_hash": "a" * 64,
        "artifacts": ["summary.md"],
    }

    adapted = LegacyPayloadAdapter.adapt_submission(legacy_submission)
    assert adapted.schema_version == SchemaVersion.V1_0
    assert adapted.submission_id == "sub_old_99"
    assert adapted.task_id == "T-GOV-001"
    assert adapted.candidate_id == "pritesh_patra"
    assert len(adapted.review_packet_hash) == 64
