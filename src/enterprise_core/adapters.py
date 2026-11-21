"""Backward compatibility adapters for legacy BHIV schemas (v0.8/v0.9 to v1.0)."""

from __future__ import annotations

import datetime
from typing import Any, Dict
from contracts.schemas import (
    SchemaVersion,
    TaskSpec,
    PriorityLevel,
    DifficultyLevel,
    ReviewSubmissionPayload,
)


class LegacyPayloadAdapter:
    """Adapts legacy schema payloads to strict v1.0 contracts."""

    @classmethod
    def adapt_task_spec(cls, legacy_dict: Dict[str, Any]) -> TaskSpec:
        """Convert v0.8/v0.9 task representation into strict TaskSpec v1.0."""
        task_id = legacy_dict.get("task_id") or legacy_dict.get("id") or "T-LEGACY-001"
        if not task_id.startswith("T-"):
            task_id = f"T-{task_id}"

        title = legacy_dict.get("title") or legacy_dict.get("name") or "Legacy Task Specification"
        department = legacy_dict.get("department") or legacy_dict.get("dept") or "AI ML"

        raw_priority = str(legacy_dict.get("priority", "MEDIUM")).upper()
        priority_map = {
            "CRITICAL": PriorityLevel.CRITICAL,
            "HIGH": PriorityLevel.HIGH,
            "MED": PriorityLevel.MEDIUM,
            "MEDIUM": PriorityLevel.MEDIUM,
            "LOW": PriorityLevel.LOW,
        }
        priority = priority_map.get(raw_priority, PriorityLevel.MEDIUM)

        raw_difficulty = str(legacy_dict.get("difficulty", "BEGINNER")).upper()
        diff_map = {
            "BEGINNER": DifficultyLevel.BEGINNER,
            "INTERMEDIATE": DifficultyLevel.INTERMEDIATE,
            "ADVANCED": DifficultyLevel.ADVANCED,
            "EXPERT": DifficultyLevel.EXPERT,
        }
        difficulty = diff_map.get(raw_difficulty, DifficultyLevel.BEGINNER)

        duration = int(legacy_dict.get("duration", legacy_dict.get("calibrated_duration_hours", 35)))
        phases = legacy_dict.get("phases") or ["Phase 1: Analysis", "Phase 2: Execution", "Phase 3: Verification"]
        criteria = legacy_dict.get("criteria") or legacy_dict.get("acceptance_criteria") or ["100% test pass rate"]
        spec_body = legacy_dict.get("body") or legacy_dict.get("canonical_spec_body") or (
            f"Canonical specification for {task_id}: {title}. Satisfies SETU OS Architecture v6.0."
        )

        return TaskSpec(
            schema_version=SchemaVersion.V1_0,
            task_id=task_id,
            title=title,
            department=department,
            priority=priority,
            calibrated_duration_hours=duration,
            difficulty_level=difficulty,
            phases=phases,
            acceptance_criteria=criteria,
            canonical_spec_body=spec_body,
        )

    @classmethod
    def adapt_submission(cls, legacy_dict: Dict[str, Any]) -> ReviewSubmissionPayload:
        """Convert legacy submission format to ReviewSubmissionPayload v1.0."""
        submission_id = legacy_dict.get("submission_id") or legacy_dict.get("sub_id") or "sub_legacy_001"
        task_id = legacy_dict.get("task_id") or "T-GOV-001"
        if not task_id.startswith("T-"):
            task_id = f"T-{task_id}"

        candidate_id = legacy_dict.get("candidate_id") or legacy_dict.get("author") or "candidate_pritesh"
        commit_hash = legacy_dict.get("commit_hash") or legacy_dict.get("commit") or "a1b2c3d4e5f67890"
        repo_url = legacy_dict.get("repo_url") or legacy_dict.get("repository_url") or "https://github.com/bhiv/core"
        
        # Ensure 64-char hex hash
        packet_hash = legacy_dict.get("review_packet_hash") or legacy_dict.get("packet_hash")
        if not packet_hash or len(packet_hash) != 64:
            packet_hash = "e" * 64

        artifacts = legacy_dict.get("artifacts") or legacy_dict.get("evidence_artifacts") or []

        return ReviewSubmissionPayload(
            schema_version=SchemaVersion.V1_0,
            submission_id=submission_id,
            task_id=task_id,
            candidate_id=candidate_id,
            commit_hash=commit_hash,
            repository_url=repo_url,
            review_packet_hash=packet_hash,
            evidence_artifacts=artifacts,
            submitted_at=datetime.datetime.now(datetime.timezone.utc),
        )
