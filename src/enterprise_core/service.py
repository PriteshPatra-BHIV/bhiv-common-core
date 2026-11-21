"""Enterprise Core Domain Service coordinating task lifecycle, governance and audit."""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Dict, List, Optional

from contracts.schemas import (
    TaskState,
    TaskSpec,
    ReviewSubmissionPayload,
    EvaluationSubmissionPayload,
    EvaluationVerdict,
    NextTaskAssignmentRequest,
    NiyantranAssignmentResponse,
    SchemaVersion,
)
from src.enterprise_core.models import TaskAggregate, ConcurrencyError
from src.enterprise_core.state_machine import DeterministicStateMachine, TaskEvent
from src.enterprise_core.ledger import ReplayLedger


class EnterpriseCoreService:
    """Production Enterprise Core service adhering to SETU OS Architecture v6.0."""

    def __init__(self, ledger: Optional[ReplayLedger] = None) -> None:
        self.ledger = ledger or ReplayLedger()
        self._tasks: Dict[str, TaskAggregate] = {}
        self._idempotency_cache: Dict[str, Any] = {}

    def get_task(self, task_id: str) -> Optional[TaskAggregate]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[TaskAggregate]:
        return list(self._tasks.values())

    def create_task(self, spec: TaskSpec, actor_id: str) -> TaskAggregate:
        """Create new canonical task in DRAFT state."""
        task = TaskAggregate(
            task_id=spec.task_id,
            title=spec.title,
            state=TaskState.DRAFT,
            version=1,
            spec=spec,
        )
        self._tasks[spec.task_id] = task

        self.ledger.record_event(
            event_type="TASK_CREATED",
            aggregate_id=spec.task_id,
            aggregate_version=1,
            actor_id=actor_id,
            details={"task_id": spec.task_id, "title": spec.title, "state": TaskState.DRAFT.value},
        )
        return task

    def submit_review(
        self,
        submission: ReviewSubmissionPayload,
        expected_version: int,
        actor_id: str,
    ) -> TaskAggregate:
        """Process candidate repository submission and transition to SUBMITTED."""
        task = self._tasks.get(submission.task_id)
        if not task:
            raise ValueError(f"Task {submission.task_id} not found.")

        next_state = DeterministicStateMachine.transition(task.state, TaskEvent.SUBMIT)
        task.apply_state_transition(
            new_state=next_state,
            expected_version=expected_version,
            submission=submission,
        )

        self.ledger.record_event(
            event_type="REVIEW_SUBMITTED",
            aggregate_id=task.task_id,
            aggregate_version=task.version,
            actor_id=actor_id,
            details={
                "submission_id": submission.submission_id,
                "commit_hash": submission.commit_hash,
                "review_packet_hash": submission.review_packet_hash,
                "state": next_state.value,
            },
        )
        return task

    def start_review(self, task_id: str, expected_version: int, reviewer_id: str) -> TaskAggregate:
        """Reviewer opens submission; transition to IN_REVIEW."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found.")

        next_state = DeterministicStateMachine.transition(task.state, TaskEvent.START_REVIEW)
        task.apply_state_transition(
            new_state=next_state,
            expected_version=expected_version,
        )

        self.ledger.record_event(
            event_type="REVIEW_STARTED",
            aggregate_id=task.task_id,
            aggregate_version=task.version,
            actor_id=reviewer_id,
            details={"task_id": task_id, "reviewer_id": reviewer_id, "state": next_state.value},
        )
        return task

    def evaluate_submission(
        self,
        evaluation: EvaluationSubmissionPayload,
        expected_version: int,
        actor_id: str,
    ) -> TaskAggregate:
        """Record Parikshak evaluation verdict and transition state."""
        # Find task by submission id
        target_task: Optional[TaskAggregate] = None
        for task in self._tasks.values():
            if task.submission and task.submission.submission_id == evaluation.submission_id:
                target_task = task
                break

        if not target_task:
            raise ValueError(f"Submission {evaluation.submission_id} not associated with any active task.")

        event = TaskEvent.EVALUATE_PASS if evaluation.verdict in (
            EvaluationVerdict.PASS,
            EvaluationVerdict.CONDITIONAL,
        ) else TaskEvent.EVALUATE_FAIL

        next_state = DeterministicStateMachine.transition(
            current_state=target_task.state,
            event=event,
            score=evaluation.score,
            verdict=evaluation.verdict,
        )

        target_task.apply_state_transition(
            new_state=next_state,
            expected_version=expected_version,
            evaluation=evaluation,
        )

        self.ledger.record_event(
            event_type="EVALUATION_RECORDED",
            aggregate_id=target_task.task_id,
            aggregate_version=target_task.version,
            actor_id=actor_id,
            details={
                "verdict": evaluation.verdict.value,
                "score": evaluation.score,
                "state": next_state.value,
                "signature": evaluation.signature,
            },
        )
        return target_task

    def assign_next_task(
        self,
        request: NextTaskAssignmentRequest,
        expected_version: int,
        actor_id: str,
    ) -> NiyantranAssignmentResponse:
        """Execute Zero-Context-Switch next task assignment via Niyantran orchestration."""
        # Check idempotency
        if request.idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[request.idempotency_key]

        target_task: Optional[TaskAggregate] = None
        for task in self._tasks.values():
            if task.submission and task.submission.submission_id == request.submission_id:
                target_task = task
                break

        if not target_task:
            raise ValueError(f"Submission {request.submission_id} not found.")

        # Transition to ASSIGNED
        next_state = DeterministicStateMachine.transition(
            current_state=target_task.state,
            event=TaskEvent.ASSIGN_NEXT,
        )

        # Generate assignment response
        assignment_id = f"asgn_{hashlib.sha256(request.idempotency_key.encode()).hexdigest()[:16]}"
        gov_os_tx = f"0x{hashlib.sha256((assignment_id + request.next_task_id).encode()).hexdigest()}"
        bucket_uri = f"s3://bhiv-bucket-evidence/assignments/{assignment_id}.json"

        assignment_resp = NiyantranAssignmentResponse(
            schema_version=SchemaVersion.V1_0,
            assignment_id=assignment_id,
            task_id=request.next_task_id,
            candidate_id=request.assignee_candidate_id,
            assigned_at=datetime.datetime.now(datetime.timezone.utc),
            target_date=request.target_date,
            canonical_depth_verified=True,
            sync_status="SYNCHRONIZED",
            gov_os_tx_hash=gov_os_tx,
            bucket_evidence_uri=bucket_uri,
        )

        target_task.apply_state_transition(
            new_state=next_state,
            expected_version=expected_version,
            assignment=assignment_resp,
        )

        self.ledger.record_event(
            event_type="NIYANTRAN_TASK_ASSIGNED",
            aggregate_id=target_task.task_id,
            aggregate_version=target_task.version,
            actor_id=actor_id,
            details={
                "assignment_id": assignment_id,
                "next_task_id": request.next_task_id,
                "assignee": request.assignee_candidate_id,
                "gov_os_tx_hash": gov_os_tx,
                "state": next_state.value,
            },
        )

        # Cache response for idempotency
        self._idempotency_cache[request.idempotency_key] = assignment_resp
        return assignment_resp
