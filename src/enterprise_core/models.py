"""Domain data models and aggregate roots for BHIV Enterprise Core."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from contracts.schemas import (
    TaskState,
    TaskSpec,
    ReviewSubmissionPayload,
    EvaluationSubmissionPayload,
    NiyantranAssignmentResponse,
)


class ConcurrencyError(Exception):
    """Raised when Optimistic Concurrency Control (OCC) detects a version mismatch."""
    pass


class UnauthorizedDirectMutationError(Exception):
    """Raised when direct property mutation is attempted bypassing the state machine."""
    pass


class TaskAggregate(BaseModel):
    """Aggregate root representing an enterprise task and its governed lifecycle."""

    task_id: str
    title: str
    state: TaskState = TaskState.DRAFT
    version: int = Field(default=1, ge=1)
    spec: TaskSpec
    candidate_id: Optional[str] = None
    submission: Optional[ReviewSubmissionPayload] = None
    evaluation: Optional[EvaluationSubmissionPayload] = None
    assignment: Optional[NiyantranAssignmentResponse] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(validate_assignment=True)

    def check_version(self, expected_version: int) -> None:
        """Verify optimistic concurrency control version."""
        if self.version != expected_version:
            raise ConcurrencyError(
                f"OCC conflict on Task {self.task_id}: expected version {expected_version}, "
                f"current version is {self.version}."
            )

    def apply_state_transition(
        self,
        new_state: TaskState,
        expected_version: int,
        submission: Optional[ReviewSubmissionPayload] = None,
        evaluation: Optional[EvaluationSubmissionPayload] = None,
        assignment: Optional[NiyantranAssignmentResponse] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Apply state transition with OCC version increment."""
        self.check_version(expected_version)
        self.state = new_state
        self.version += 1
        self.updated_at = datetime.datetime.now(datetime.timezone.utc)

        if submission is not None:
            self.submission = submission
            self.candidate_id = submission.candidate_id
        if evaluation is not None:
            self.evaluation = evaluation
        if assignment is not None:
            self.assignment = assignment
        if metadata_update:
            self.metadata.update(metadata_update)
