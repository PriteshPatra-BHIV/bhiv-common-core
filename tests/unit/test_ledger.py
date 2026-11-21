"""Tier 1 Unit Tests: Cryptographic Replay Ledger and event sourcing verification."""

from __future__ import annotations

import datetime
from src.enterprise_core.ledger import ReplayLedger, GENESIS_HASH


def test_ledger_initialization_and_genesis() -> None:
    """Verify ledger starts with genesis hash and zero events."""
    ledger = ReplayLedger()
    assert ledger.current_state_hash == GENESIS_HASH
    assert ledger.event_count == 0


def test_ledger_event_chaining_and_verification() -> None:
    """Verify continuous SHA-256 state hash chaining."""
    ledger = ReplayLedger()
    fixed_time = datetime.datetime(2026, 11, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)

    evt1 = ledger.record_event(
        event_type="TASK_CREATED",
        aggregate_id="T-GOV-002",
        aggregate_version=1,
        actor_id="usr_admin",
        details={"title": "Test Task"},
        fixed_event_id="evt_00001",
        fixed_timestamp=fixed_time,
    )
    assert evt1.prev_state_hash == GENESIS_HASH
    assert evt1.state_hash != GENESIS_HASH
    assert len(evt1.state_hash) == 64

    evt2 = ledger.record_event(
        event_type="REVIEW_SUBMITTED",
        aggregate_id="T-GOV-002",
        aggregate_version=2,
        actor_id="usr_pritesh",
        details={"commit_hash": "a1b2c3d4"},
        fixed_event_id="evt_00002",
        fixed_timestamp=fixed_time,
    )
    assert evt2.prev_state_hash == evt1.state_hash
    assert len(evt2.state_hash) == 64

    is_valid, final_hash = ledger.replay_and_verify()
    assert is_valid is True
    assert final_hash == evt2.state_hash


def test_ledger_tamper_detection() -> None:
    """Verify that tampering with an event's details breaks replay verification."""
    ledger = ReplayLedger()
    ledger.record_event(
        event_type="TASK_CREATED",
        aggregate_id="T-GOV-002",
        aggregate_version=1,
        actor_id="usr_admin",
        details={"title": "Legitimate Title"},
        fixed_event_id="evt_tamper_1",
    )

    # Artificially alter the stored event payload
    ledger._events[0].details["title"] = "Tampered Title"

    is_valid, reason = ledger.replay_and_verify()
    assert is_valid is False
    assert "Payload hash mismatch" in reason
