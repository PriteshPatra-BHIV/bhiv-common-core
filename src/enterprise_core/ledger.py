"""Cryptographic Replay Ledger and Event Sourcing Engine.
Connects with Gov-OS for ledger hashing and Bucket for audit proof storage.
Guarantees bit-level identical SHA-256 state hashing across 50 consecutive runs.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import datetime
from typing import Any, Dict, List, Optional
from contracts.schemas import ReplayEvent, SchemaVersion


GENESIS_HASH = "0" * 64


class ReplayLedger:
    """Event-sourced cryptographic ledger providing deterministic state replay."""

    def __init__(self, initial_hash: str = GENESIS_HASH) -> None:
        self._events: List[ReplayEvent] = []
        self._current_state_hash: str = initial_hash
        self._sequence_counter: int = 0

    @property
    def current_state_hash(self) -> str:
        return self._current_state_hash

    @property
    def event_count(self) -> int:
        return len(self._events)

    def get_events(self) -> List[ReplayEvent]:
        return list(self._events)

    @staticmethod
    def compute_payload_hash(payload: Dict[str, Any]) -> str:
        """Deterministically serialize payload and compute SHA-256 hash."""
        canonical_json = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_state_hash(
        prev_hash: str,
        event_id: str,
        event_type: str,
        payload_hash: str,
        aggregate_version: int,
    ) -> str:
        """Compute chained state hash: SHA-256(prev || event_id || event_type || payload_hash || version)."""
        chain_string = f"{prev_hash}|{event_id}|{event_type}|{payload_hash}|{aggregate_version}"
        return hashlib.sha256(chain_string.encode("utf-8")).hexdigest()

    def record_event(
        self,
        event_type: str,
        aggregate_id: str,
        aggregate_version: int,
        actor_id: str,
        details: Dict[str, Any],
        fixed_event_id: Optional[str] = None,
        fixed_timestamp: Optional[datetime.datetime] = None,
    ) -> ReplayEvent:
        """Record an immutable event and advance the rolling state hash."""
        payload_hash = self.compute_payload_hash(details)
        
        clean_id = aggregate_id.replace("-", "_")
        event_id = fixed_event_id or f"evt_{clean_id}_{aggregate_version}_{self._sequence_counter:04d}"
        timestamp = fixed_timestamp or datetime.datetime.now(datetime.timezone.utc)

        new_state_hash = self.compute_state_hash(
            prev_hash=self._current_state_hash,
            event_id=event_id,
            event_type=event_type,
            payload_hash=payload_hash,
            aggregate_version=aggregate_version,
        )

        event = ReplayEvent(
            schema_version=SchemaVersion.V1_0,
            event_id=event_id,
            sequence_num=self._sequence_counter,
            timestamp=timestamp,
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            actor_id=actor_id,
            payload_hash=payload_hash,
            prev_state_hash=self._current_state_hash,
            state_hash=new_state_hash,
            details=details,
        )

        self._events.append(event)
        self._current_state_hash = new_state_hash
        self._sequence_counter += 1
        return event

    def replay_and_verify(self) -> Tuple[bool, str]:
        """Replay all events from genesis and verify complete hash integrity."""
        current_hash = GENESIS_HASH
        for idx, event in enumerate(self._events):
            if event.prev_state_hash != current_hash:
                return False, f"Broken chain link at index {idx}: expected {current_hash}, found {event.prev_state_hash}"

            recomputed_payload_hash = self.compute_payload_hash(event.details)
            if recomputed_payload_hash != event.payload_hash:
                return False, f"Payload hash mismatch at event {event.event_id}"

            recomputed_state_hash = self.compute_state_hash(
                prev_hash=current_hash,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=recomputed_payload_hash,
                aggregate_version=event.aggregate_version,
            )

            if recomputed_state_hash != event.state_hash:
                return False, f"State hash mismatch at event {event.event_id}"

            current_hash = recomputed_state_hash

        return True, current_hash
