"""Tier 1 Unit Tests: Deterministic Finite State Machine traversal and invariants."""

from __future__ import annotations

import pytest
from contracts.schemas import TaskState, EvaluationVerdict
from src.enterprise_core.state_machine import (
    DeterministicStateMachine,
    TaskEvent,
    StateTransitionError,
)


def test_fsm_valid_lifecycle_progression() -> None:
    """Verify the canonical state path: DRAFT -> SUBMITTED -> IN_REVIEW -> EVALUATION_PASS -> ASSIGNED -> SYNCHRONIZED -> ARCHIVED."""
    state = TaskState.DRAFT

    state = DeterministicStateMachine.transition(state, TaskEvent.SUBMIT)
    assert state == TaskState.SUBMITTED

    state = DeterministicStateMachine.transition(state, TaskEvent.START_REVIEW)
    assert state == TaskState.IN_REVIEW

    state = DeterministicStateMachine.transition(
        state,
        TaskEvent.EVALUATE_PASS,
        score=95,
        verdict=EvaluationVerdict.PASS,
    )
    assert state == TaskState.EVALUATION_PASS

    state = DeterministicStateMachine.transition(state, TaskEvent.ASSIGN_NEXT)
    assert state == TaskState.ASSIGNED

    state = DeterministicStateMachine.transition(state, TaskEvent.SYNC_NIYANTRAN)
    assert state == TaskState.SYNCHRONIZED

    state = DeterministicStateMachine.transition(state, TaskEvent.ARCHIVE)
    assert state == TaskState.ARCHIVED


def test_fsm_illegal_transition_rejection() -> None:
    """Verify attempting to jump states directly raises StateTransitionError."""
    # Cannot jump from DRAFT to ASSIGNED
    with pytest.raises(StateTransitionError):
        DeterministicStateMachine.transition(TaskState.DRAFT, TaskEvent.ASSIGN_NEXT)

    # Cannot jump from SUBMITTED to EVALUATE_PASS without START_REVIEW
    with pytest.raises(StateTransitionError):
        DeterministicStateMachine.transition(
            TaskState.SUBMITTED,
            TaskEvent.EVALUATE_PASS,
            score=90,
            verdict=EvaluationVerdict.PASS,
        )


def test_fsm_evaluate_pass_requires_minimum_score() -> None:
    """Verify EVALUATE_PASS rejects score < 70 (addressing incorrect_logic focus)."""
    with pytest.raises(StateTransitionError, match="requires score >= 70"):
        DeterministicStateMachine.transition(
            TaskState.IN_REVIEW,
            TaskEvent.EVALUATE_PASS,
            score=65,
            verdict=EvaluationVerdict.PASS,
        )


def test_fsm_evaluation_fail_path() -> None:
    """Verify failing review path and subsequent resubmission."""
    state = TaskState.IN_REVIEW
    state = DeterministicStateMachine.transition(
        state,
        TaskEvent.EVALUATE_FAIL,
        score=40,
        verdict=EvaluationVerdict.FAIL,
    )
    assert state == TaskState.EVALUATION_FAIL

    # Candidate retries submission
    resubmitted_state = DeterministicStateMachine.transition(state, TaskEvent.RETRY_SUBMISSION)
    assert resubmitted_state == TaskState.SUBMITTED
