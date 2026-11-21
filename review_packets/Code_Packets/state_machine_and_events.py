"""Reference Code Packet: State Machine, Optimistic Concurrency Control, and Replay Ledger."""

from src.enterprise_core.state_machine import (
    DeterministicStateMachine,
    TaskEvent,
    StateTransitionError,
    TRANSITION_RULES,
)
from src.enterprise_core.models import (
    TaskAggregate,
    ConcurrencyError,
    UnauthorizedDirectMutationError,
)
from src.enterprise_core.ledger import (
    ReplayLedger,
    GENESIS_HASH,
)

__all__ = [
    "DeterministicStateMachine",
    "TaskEvent",
    "StateTransitionError",
    "TRANSITION_RULES",
    "TaskAggregate",
    "ConcurrencyError",
    "UnauthorizedDirectMutationError",
    "ReplayLedger",
    "GENESIS_HASH",
]
