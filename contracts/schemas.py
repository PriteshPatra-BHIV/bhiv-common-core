"""BHIV Enterprise Operating System Common Core Contracts.
Strict schema v1.0 interface definitions conforming to SETU OS Architecture v6.0.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator


class SchemaVersion(str, Enum):
    V1_0 = "1.0"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    GOVERNANCE_OFFICER = "GOVERNANCE_OFFICER"
    CANDIDATE = "CANDIDATE"
    AUDITOR = "AUDITOR"


class TaskState(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    EVALUATION_PASS = "EVALUATION_PASS"
    EVALUATION_FAIL = "EVALUATION_FAIL"
    ASSIGNED = "ASSIGNED"
    SYNCHRONIZED = "SYNCHRONIZED"
    ARCHIVED = "ARCHIVED"


class EvaluationVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"


class PriorityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DifficultyLevel(str, Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"


# ---------------------------------------------------------
# Core Identity & Authentication Contracts
# ---------------------------------------------------------

class AuthTokenPayload(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    token: str = Field(..., min_length=16, description="Cryptographic bearer token")
    user_id: str = Field(..., min_length=3, description="Canonical subject identifier")
    role: UserRole
    scopes: List[str] = Field(default_factory=list)
    issued_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    expires_at: datetime.datetime = Field(..., description="Expiration UTC timestamp")

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, v: datetime.datetime, info: Any) -> datetime.datetime:
        return v


class TokenIntrospectRequest(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    token: str = Field(..., min_length=16)


class TokenIntrospectResponse(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    active: bool
    user_id: Optional[str] = None
    role: Optional[UserRole] = None
    scopes: List[str] = Field(default_factory=list)
    remaining_seconds: Optional[int] = None


# ---------------------------------------------------------
# Task & Review Lifecycle Contracts
# ---------------------------------------------------------

class CandidateProfile(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    candidate_id: str = Field(..., min_length=3)
    name: str = Field(..., min_length=2)
    department: str = Field(default="AI ML")
    maturity_level: str = Field(default="Junior Associate")
    learning_velocity: float = Field(default=-4.0)
    weakness_focus: str = Field(default="incorrect_logic")


class TaskSpec(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    task_id: str = Field(..., pattern=r"^T-[A-Z0-9_-]+$")
    title: str = Field(..., min_length=5)
    department: str = Field(default="AI ML")
    priority: PriorityLevel = PriorityLevel.MEDIUM
    calibrated_duration_hours: int = Field(default=35, ge=1, le=168)
    difficulty_level: DifficultyLevel = DifficultyLevel.BEGINNER
    phases: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    canonical_spec_body: str = Field(..., min_length=20)


class ReviewSubmissionPayload(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    submission_id: str = Field(..., min_length=5)
    task_id: str = Field(..., pattern=r"^T-[A-Z0-9_-]+$")
    candidate_id: str = Field(..., min_length=3)
    commit_hash: str = Field(..., min_length=7, max_length=64)
    repository_url: str = Field(..., min_length=8)
    review_packet_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 of review packet")
    evidence_artifacts: List[str] = Field(default_factory=list)
    submitted_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class EvaluationSubmissionPayload(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    submission_id: str = Field(..., min_length=5)
    reviewer_id: str = Field(..., min_length=3)
    verdict: EvaluationVerdict
    score: int = Field(..., ge=0, le=100)
    findings: str = Field(..., min_length=10)
    weaknesses_flagged: List[str] = Field(default_factory=list)
    signature: str = Field(..., min_length=16, description="Cryptographic reviewer signature")


class NextTaskAssignmentRequest(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    submission_id: str = Field(..., min_length=5)
    reviewer_id: str = Field(..., min_length=3)
    next_task_id: str = Field(..., pattern=r"^T-[A-Z0-9_-]+$")
    assignee_candidate_id: str = Field(..., min_length=3)
    target_date: datetime.date
    priority: PriorityLevel = PriorityLevel.MEDIUM
    idempotency_key: str = Field(..., min_length=16)


class NiyantranAssignmentResponse(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    assignment_id: str
    task_id: str
    candidate_id: str
    assigned_at: datetime.datetime
    target_date: datetime.date
    canonical_depth_verified: bool = True
    sync_status: str = "SYNCHRONIZED"
    gov_os_tx_hash: str
    bucket_evidence_uri: str


# ---------------------------------------------------------
# Replay Ledger & Event Sourcing Contracts
# ---------------------------------------------------------

class ReplayEvent(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    event_id: str = Field(..., min_length=8)
    sequence_num: int = Field(..., ge=0)
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    event_type: str = Field(..., min_length=3)
    aggregate_id: str = Field(..., min_length=3)
    aggregate_version: int = Field(..., ge=1)
    actor_id: str = Field(..., min_length=3)
    payload_hash: str = Field(..., min_length=64, max_length=64)
    prev_state_hash: str = Field(..., min_length=64, max_length=64)
    state_hash: str = Field(..., min_length=64, max_length=64)
    details: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------
# Standard Response Envelope & Error Boundary
# ---------------------------------------------------------

T = TypeVar("T")

class StandardResponseEnvelope(BaseModel, Generic[T]):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    status: str = "SUCCESS"
    data: Optional[T] = None
    error: Optional[Dict[str, Any]] = None
    trace_id: str
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class ProblemDetails(BaseModel):
    schema_version: SchemaVersion = SchemaVersion.V1_0
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    invalid_params: Optional[List[Dict[str, Any]]] = None
