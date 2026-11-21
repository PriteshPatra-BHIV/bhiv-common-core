"""API Routes for BHIV Enterprise Core and Identity Provider."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from contracts.schemas import (
    AuthTokenPayload,
    CandidateProfile,
    EvaluationSubmissionPayload,
    NextTaskAssignmentRequest,
    NiyantranAssignmentResponse,
    ProblemDetails,
    ReplayEvent,
    ReviewSubmissionPayload,
    StandardResponseEnvelope,
    TaskSpec,
    TokenIntrospectRequest,
    TokenIntrospectResponse,
    UserRole,
    SchemaVersion,
)
from src.enterprise_core.adapters import LegacyPayloadAdapter
from src.enterprise_core.models import TaskAggregate
from src.enterprise_core.service import EnterpriseCoreService
from src.identity_provider.service import HardenedIdentityProvider
from src.integrations.gc_shakti import GCShaktiPolicyEngine
from src.integrations.niyantran import NiyantranEngine
from src.integrations.gov_os import GovOSLedgerConnector
from src.integrations.bucket import BucketStorageConnector
from src.integrations.saarthi import SaarthiVisibilityService

router = APIRouter()
core_service = EnterpriseCoreService()
idp_service = HardenedIdentityProvider()


def get_current_token(authorization: Optional[str] = Header(None)) -> AuthTokenPayload:
    """Bearer token verification dependency."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <token>'.",
        )
    raw_token = authorization.split(" ", 1)[1].strip()
    return idp_service.verify_token(raw_token)


# ---------------------------------------------------------
# Health & Service Discovery Endpoints
# ---------------------------------------------------------

@router.get("/health")
def api_v1_health() -> Dict[str, Any]:
    """Pre-flight service discovery and health check."""
    return {
        "status": "UP",
        "name": "bhiv-common-core",
        "version": SchemaVersion.V1_0.value,
        "task_id": "T-GOV-002",
        "standard": "SETU OS Architecture v6.0",
    }


# ---------------------------------------------------------
# Identity Provider Endpoints
# ---------------------------------------------------------

@router.post("/auth/token", response_model=StandardResponseEnvelope[AuthTokenPayload])
def issue_token(
    user_id: str = Query(..., description="Subject user identifier"),
    role: UserRole = Query(UserRole.REVIEWER, description="Role to assign"),
    ttl_seconds: int = Query(3600, ge=60, le=86400),
) -> StandardResponseEnvelope[AuthTokenPayload]:
    """Issue a tamper-evident, cryptographically signed token."""
    token = idp_service.issue_token(user_id=user_id, role=role, ttl_seconds=ttl_seconds)
    return StandardResponseEnvelope(
        data=token,
        trace_id=f"tr_{uuid.uuid4().hex[:10]}",
    )


@router.post("/auth/introspect", response_model=StandardResponseEnvelope[TokenIntrospectResponse])
def introspect_token(request: TokenIntrospectRequest) -> StandardResponseEnvelope[TokenIntrospectResponse]:
    """Introspect and validate an issued token."""
    try:
        token_payload = idp_service.verify_token(request.token)
        remaining = int((token_payload.expires_at - token_payload.issued_at).total_seconds())
        resp = TokenIntrospectResponse(
            active=True,
            user_id=token_payload.user_id,
            role=token_payload.role,
            scopes=token_payload.scopes,
            remaining_seconds=remaining,
        )
    except Exception:
        resp = TokenIntrospectResponse(active=False)

    return StandardResponseEnvelope(
        data=resp,
        trace_id=f"tr_{uuid.uuid4().hex[:10]}",
    )


# ---------------------------------------------------------
# Enterprise Core Task Management Endpoints
# ---------------------------------------------------------

@router.post("/tasks", response_model=StandardResponseEnvelope[TaskAggregate])
def create_task(
    spec: TaskSpec,
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskAggregate]:
    """Create a new canonical task in DRAFT state."""
    idp_service.enforce_role(token, [UserRole.ADMIN, UserRole.REVIEWER])
    task = core_service.create_task(spec=spec, actor_id=token.user_id)
    SaarthiVisibilityService.publish_event("TASK_CREATED", {"task_id": spec.task_id})
    return StandardResponseEnvelope(data=task, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.get("/tasks/{task_id}", response_model=StandardResponseEnvelope[TaskAggregate])
def get_task(
    task_id: str,
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskAggregate]:
    """Retrieve full task aggregate including lifecycle state and version."""
    task = core_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")
    return StandardResponseEnvelope(data=task, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


# ---------------------------------------------------------
# Review & Evaluation Workflow Endpoints
# ---------------------------------------------------------

@router.post("/submissions", response_model=StandardResponseEnvelope[TaskAggregate])
def submit_review(
    submission: ReviewSubmissionPayload,
    expected_version: int = Query(1, ge=1, description="OCC expected version"),
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskAggregate]:
    """Candidate submits repository for evaluation."""
    idp_service.enforce_role(token, [UserRole.CANDIDATE, UserRole.ADMIN])
    task = core_service.submit_review(
        submission=submission,
        expected_version=expected_version,
        actor_id=token.user_id,
    )
    # Store evidence reference in Bucket
    BucketStorageConnector.store_evidence(
        f"submission-{submission.submission_id}",
        submission.model_dump(mode="json"),
    )
    SaarthiVisibilityService.publish_event("SUBMISSION_RECEIVED", {"task_id": submission.task_id})
    return StandardResponseEnvelope(data=task, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.post("/reviews/start", response_model=StandardResponseEnvelope[TaskAggregate])
def start_review(
    task_id: str = Query(..., description="Task ID to start review"),
    expected_version: int = Query(..., ge=1, description="OCC expected version"),
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskAggregate]:
    """Reviewer moves task from SUBMITTED to IN_REVIEW."""
    idp_service.enforce_role(token, [UserRole.REVIEWER, UserRole.ADMIN])
    task = core_service.start_review(
        task_id=task_id,
        expected_version=expected_version,
        reviewer_id=token.user_id,
    )
    SaarthiVisibilityService.publish_event("REVIEW_STARTED", {"task_id": task_id})
    return StandardResponseEnvelope(data=task, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.post("/reviews/evaluate", response_model=StandardResponseEnvelope[TaskAggregate])
def evaluate_submission(
    evaluation: EvaluationSubmissionPayload,
    expected_version: int = Query(..., ge=1, description="OCC expected version"),
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskAggregate]:
    """Parikshak reviewer records verdict with GC Shakti policy validation."""
    idp_service.enforce_role(token, [UserRole.REVIEWER, UserRole.ADMIN])
    # Validate with GC Shakti policy authority
    GCShaktiPolicyEngine.validate_evaluation_policy(evaluation)

    task = core_service.evaluate_submission(
        evaluation=evaluation,
        expected_version=expected_version,
        actor_id=token.user_id,
    )

    # Anchor evaluation into Gov-OS ledger
    GovOSLedgerConnector.anchor_state_hash(task.task_id, core_service.ledger.current_state_hash)
    BucketStorageConnector.store_evidence(f"evaluation-{evaluation.submission_id}", evaluation.model_dump(mode="json"))
    SaarthiVisibilityService.publish_event("EVALUATION_COMPLETED", {"verdict": evaluation.verdict.value, "score": evaluation.score})

    return StandardResponseEnvelope(data=task, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.post("/reviews/assign-next", response_model=StandardResponseEnvelope[NiyantranAssignmentResponse])
def assign_next_task(
    request: NextTaskAssignmentRequest,
    expected_version: int = Query(..., ge=1, description="OCC expected version"),
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[NiyantranAssignmentResponse]:
    """Zero-Context-Switch assignment: auto-assign canonical next task via Niyantran."""
    idp_service.enforce_role(token, [UserRole.REVIEWER, UserRole.ADMIN])

    # Verify canonical depth in Niyantran database
    if not NiyantranEngine.verify_canonical_depth(request.next_task_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task {request.next_task_id} failed canonical depth check (zero placeholder IDs allowed).",
        )

    assignment = core_service.assign_next_task(
        request=request,
        expected_version=expected_version,
        actor_id=token.user_id,
    )

    GovOSLedgerConnector.anchor_state_hash(assignment.assignment_id, core_service.ledger.current_state_hash)
    BucketStorageConnector.store_evidence(f"assignment-{assignment.assignment_id}", assignment.model_dump(mode="json"))
    SaarthiVisibilityService.publish_event("TASK_ASSIGNED_NIYANTRAN", {"assignment_id": assignment.assignment_id})

    return StandardResponseEnvelope(data=assignment, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


# ---------------------------------------------------------
# Audit Ledger & Operational Telemetry
# ---------------------------------------------------------

@router.get("/ledger/events", response_model=StandardResponseEnvelope[List[ReplayEvent]])
def get_ledger_events(
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[List[ReplayEvent]]:
    """Retrieve complete event-sourced replay history."""
    events = core_service.ledger.get_events()
    return StandardResponseEnvelope(data=events, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.get("/ledger/state-hash", response_model=StandardResponseEnvelope[Dict[str, Any]])
def get_ledger_state_hash(
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[Dict[str, Any]]:
    """Retrieve current rolling SHA-256 state hash and verification status."""
    is_valid, current_hash = core_service.ledger.replay_and_verify()
    data = {
        "current_state_hash": current_hash,
        "is_valid": is_valid,
        "event_count": core_service.ledger.event_count,
    }
    return StandardResponseEnvelope(data=data, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


@router.get("/saarthi/metrics", response_model=StandardResponseEnvelope[Dict[str, Any]])
def get_saarthi_metrics(
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[Dict[str, Any]]:
    """Retrieve real-time metrics for Saarthi executive operations dashboard."""
    metrics = SaarthiVisibilityService.get_dashboard_metrics()
    return StandardResponseEnvelope(data=metrics, trace_id=f"tr_{uuid.uuid4().hex[:10]}")


# ---------------------------------------------------------
# Legacy Ingestion Adapter
# ---------------------------------------------------------

@router.post("/legacy/ingest", response_model=StandardResponseEnvelope[TaskSpec])
def ingest_legacy_task(
    payload: Dict[str, Any],
    token: AuthTokenPayload = Depends(get_current_token),
) -> StandardResponseEnvelope[TaskSpec]:
    """Ingest legacy v0.8/v0.9 payload and normalize into strict v1.0 TaskSpec."""
    adapted = LegacyPayloadAdapter.adapt_task_spec(payload)
    return StandardResponseEnvelope(data=adapted, trace_id=f"tr_{uuid.uuid4().hex[:10]}")
