# Architecture Decision Record: T-GOV-002
# BHIV Advancement Milestone: Advanced Enterprise Core & Identity Provider Hardening

## Metadata
- **Record ID:** ADR-T-GOV-002
- **Title:** Enterprise Core Capabilities, Identity Provider Hardening & Deterministic Audit Architecture
- **Status:** APPROVED & ADOPTED
- **Standard:** SETU OS Architecture v6.0
- **Target Product:** BHIV Enterprise Operating System Common Core (BHIV)
- **Assignee / Candidate:** Pritesh Patra
- **Authority:** PARIKSHAK Production Runtime Engine x NIYANTRAN Task Orchestration
- **Date:** 2026-11-21

---

## 1. Context and Problem Statement
BHIV Enterprise Operating System Common Core requires transformation from an unhardened prototype into a government-grade operational review and engineering execution platform. 

Reviewers, managers, and governance bodies require verifiable engineering truth rather than cosmetic UI summaries. Key pain points identified in previous evaluations (including candidate calibration focus on `incorrect_logic`) include:
1. Uncontrolled and unauthorized state mutations across task lifecycles.
2. Inconsistent schema validation allowing malformed payloads and potential 500 runtime faults.
3. Weak identity boundaries lacking cryptographic token verification and audit replayability.
4. Non-deterministic execution paths producing divergent state hashes across repeated evaluation cycles.
5. High cognitive friction for engineering managers reviewing submissions, leading to context-switching during next-task assignment.

---

## 2. Decision Drivers
- **Zero-Context-Switch Operational Flow:** Reviewers must be able to inspect candidate code, evaluate verification proofs, and auto-assign canonical multi-phase next tasks within 60 seconds from a single unified review interface.
- **SETU OS Architecture v6.0 Compliance:** Seamless integration across the six foundational pillars:
  - **BHIV Enterprise Common Core:** Primary system execution & state management.
  - **GC Shakti:** Governance intelligence & policy authority gatekeeping.
  - **Niyantran:** Task assignment & workflow lifecycle engine.
  - **Bucket:** Immutable evidence & audit object storage.
  - **Gov-OS:** Cryptographic governance ledger & state verification.
  - **Saarthi:** Visibility layer & executive oversight telemetry.
- **Strict Inbound & Outbound Schemas (v1.0):** Elimination of untyped payloads. Every message, submission, token, and assignment strictly adheres to Pydantic v1.0 contracts.
- **Deterministic State Machine (FSM):** Elimination of `incorrect_logic` vulnerabilities via a formal, mathematically verified transition matrix with zero unauthorized direct mutations.
- **Optimistic Concurrency Control (OCC) & Idempotency:** Version-fenced state updates and unique idempotency keys preventing race conditions and double-assignments.
- **50-Run SHA-256 State Determinism:** Verifiable cryptographic parity across 50 consecutive runs of identical event series.

---

## 3. Architectural Decisions

### 3.1 Strict Schema Enforcement (v1.0)
All inbound API requests and outbound event payloads validate against strict Pydantic v2 schemas pinned to schema version `1.0`. Any schema divergence or extraneous unvalidated field is intercepted at the API perimeter, returning an RFC-7807 compliant problem response with HTTP 422/400 and zero unhandled 500 server errors.

### 3.2 Hardened Identity Provider (IdP) & Role-Based Access Control
The embedded Identity Provider issues tamper-evident, cryptographically signed access tokens containing claims for `user_id`, `role`, `scopes`, and `issued_at`/`expires_at` timestamps.
- **Roles:** `ADMIN`, `REVIEWER`, `GOVERNANCE_OFFICER`, `CANDIDATE`, `AUDITOR`.
- **Enforcement:** Middleware validates token signatures, expiration, and role privileges before dispatching to business logic.
- **Tamper Protection:** Invalidation upon signature mismatch or timestamp drift.

### 3.3 Deterministic Finite State Machine (FSM)
The task lifecycle is governed by an immutable state machine:
```
[DRAFT] --> [SUBMITTED] --> [IN_REVIEW] --> [EVALUATION_PASS / EVALUATION_FAIL]
                                   |
                                   v
                             [ASSIGNED] --> [SYNCHRONIZED] --> [ARCHIVED]
```
- Direct property reassignment (e.g., `task.state = "APPROVED"`) is forbidden.
- All mutations occur via pure transition functions: `transition(current_state, event, context) -> (next_state, event_record)`.
- Illegal transitions trigger a `StateTransitionError` and append an audit anomaly event to Gov-OS.

### 3.4 Concurrency Control & Idempotency
- **Optimistic Concurrency Control:** Every task aggregate possesses an integer `version`. Updates specify the expected current version; mismatches reject with HTTP 409 Conflict.
- **Idempotency Keys:** Mutating endpoints require an `Idempotency-Key` header. Requests processed within the TTL return identical cached responses without re-executing state side-effects.

### 3.5 Cryptographically Linked Replay Ledger (Gov-OS & Bucket)
Every state change creates an immutable `ReplayEvent` composed of:
$$\text{state\_hash}_n = \text{SHA-256}(\text{state\_hash}_{n-1} \parallel \text{event\_id} \parallel \text{event\_type} \parallel \text{payload\_hash} \parallel \text{version})$$
This guarantees complete replayability: replaying all recorded events from genesis state reconstructs the exact same state and hash.

### 3.6 Zero-Context-Switch Niyantran Task Orchestration
Upon review approval, the system directly calls Niyantran to pull the canonical next task from the canonical task database (complete multi-phase specification with zero placeholder IDs) and assigns it to the candidate in a single atomic transaction.

---

## 4. Consequences and Mitigations

| Consequence | Severity | Mitigation |
| :--- | :--- | :--- |
| Strict schema validation rejects legacy formats | Medium | Implemented `LegacyPayloadAdapter` to normalize older v0.8/v0.9 payloads into canonical v1.0 format transparently. |
| Cryptographic state hashing adds microsecond latency | Low | SHA-256 calculation overhead is <0.02ms per event; well within the 50ms SLA budget. |
| In-memory store volatility in tests | Low | Abstracted ledger interface allowing swap between in-memory mock and distributed Gov-OS ledger while preserving identical hashing logic. |

---

## 5. Verification & Compliance Standards
1. **5-Tier Automated Test Matrix:**
   - Tier 1: Unit tests (`tests/unit/`) - Schema validation, FSM invariants, IdP token crypto.
   - Tier 2: Integration tests (`tests/integration/`) - Niyantran sync, Gov-OS chaining, Saarthi telemetry.
   - Tier 3: Negative tests (`tests/negative/`) - Tampered tokens, malformed payloads, OCC collisions, 0 unhandled 500s.
   - Tier 4: Regression tests (`tests/regression/`) - Legacy payload compatibility, multi-cycle state preservation.
   - Tier 5: End-to-End tests (`tests/e2e/`) - Full review and auto-assignment journey.
2. **50-Run SHA-256 Benchmark:**
   - 50 consecutive runs execute identical event streams.
   - All 50 runs must yield identical root state hashes: $\text{Hash}_1 \equiv \text{Hash}_2 \equiv \dots \equiv \text{Hash}_{50}$.
