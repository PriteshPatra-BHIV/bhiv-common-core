"""Deterministic Finite State Machine (FSM) for BHIV Enterprise Operating System.
Guarantees strict lifecycle traversal with zero unauthorized direct mutations.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set, Tuple
from contracts.schemas import TaskState, EvaluationVerdict


class StateTransitionError(Exception):
    """Raised when an illegal or unauthorized state transition is requested."""
    pass


class TaskEvent(str, Enum):
    SUBMIT = "SUBMIT"
    START_REVIEW = "START_REVIEW"
    EVALUATE_PASS = "EVALUATE_PASS"
    EVALUATE_FAIL = "EVALUATE_FAIL"
    ASSIGN_NEXT = "ASSIGN_NEXT"
    SYNC_NIYANTRAN = "SYNC_NIYANTRAN"
    ARCHIVE = "ARCHIVE"
    RETRY_SUBMISSION = "RETRY_SUBMISSION"


# Formal State Transition Matrix: (Current State, Event) -> Target State
TRANSITION_RULES: Dict[Tuple[TaskState, TaskEvent], TaskState] = {
    (TaskState.DRAFT, TaskEvent.SUBMIT): TaskState.SUBMITTED,
    (TaskState.SUBMITTED, TaskEvent.START_REVIEW): TaskState.IN_REVIEW,
    (TaskState.IN_REVIEW, TaskEvent.EVALUATE_PASS): TaskState.EVALUATION_PASS,
    (TaskState.IN_REVIEW, TaskEvent.EVALUATE_FAIL): TaskState.EVALUATION_FAIL,
    (TaskState.EVALUATION_PASS, TaskEvent.ASSIGN_NEXT): TaskState.ASSIGNED,
    (TaskState.ASSIGNED, TaskEvent.SYNC_NIYANTRAN): TaskState.SYNCHRONIZED,
    (TaskState.SYNCHRONIZED, TaskEvent.ARCHIVE): TaskState.ARCHIVED,
    (TaskState.EVALUATION_FAIL, TaskEvent.RETRY_SUBMISSION): TaskState.SUBMITTED,
}


class DeterministicStateMachine:
    """Mathematical state machine enforcing determinism and policy guards."""

    @classmethod
    def get_allowed_events(cls, current_state: TaskState) -> Set[TaskEvent]:
        """Returns the exact set of legal events from the current state."""
        return {event for (state, event) in TRANSITION_RULES.keys() if state == current_state}

    @classmethod
    def transition(
        cls,
        current_state: TaskState,
        event: TaskEvent,
        score: int | None = None,
        verdict: EvaluationVerdict | None = None,
    ) -> TaskState:
        """Validate pre-conditions and compute deterministic next state."""
        lookup_key = (current_state, event)
        if lookup_key not in TRANSITION_RULES:
            allowed = [e.value for e in cls.get_allowed_events(current_state)]
            raise StateTransitionError(
                f"Illegal transition: Cannot execute event '{event.value}' from state '{current_state.value}'. "
                f"Permitted events: {allowed}"
            )

        # Invariant checks for evaluation events
        if event == TaskEvent.EVALUATE_PASS:
            if score is None or score < 70:
                raise StateTransitionError(
                    f"EVALUATE_PASS requires score >= 70; received score={score}."
                )
            if verdict not in (EvaluationVerdict.PASS, EvaluationVerdict.CONDITIONAL):
                raise StateTransitionError(
                    f"EVALUATE_PASS requires verdict PASS or CONDITIONAL; received verdict={verdict}."
                )
        elif event == TaskEvent.EVALUATE_FAIL:
            if score is not None and score >= 70 and verdict == EvaluationVerdict.PASS:
                raise StateTransitionError(
                    f"EVALUATE_FAIL cannot be applied when score={score} and verdict={verdict}."
                )

        target_state = TRANSITION_RULES[lookup_key]
        return target_state
