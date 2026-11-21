"""RFC-7807 Compliant Error Handlers for BHIV Enterprise Core API.
Guarantees complete error boundary coverage with zero unhandled 500 crashes.
"""

from __future__ import annotations

import uuid
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from contracts.schemas import ProblemDetails, SchemaVersion
from src.enterprise_core.models import ConcurrencyError, UnauthorizedDirectMutationError
from src.enterprise_core.state_machine import StateTransitionError
from src.identity_provider.service import SecurityAnomalyError, TokenExpiredError
from src.integrations.gc_shakti import PolicyViolationError


def create_problem_response(
    status_code: int,
    title: str,
    detail: str,
    instance: str,
    invalid_params: list | None = None,
) -> JSONResponse:
    """Format RFC-7807 Problem Details response."""
    problem = ProblemDetails(
        schema_version=SchemaVersion.V1_0,
        type=f"https://bhiv.gov.in/errors/{title.lower().replace(' ', '-')}",
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        invalid_params=invalid_params,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json"),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic schema validation errors with HTTP 422."""
    invalid_params = []
    for err in exc.errors():
        invalid_params.append({
            "name": ".".join(str(loc) for loc in err["loc"]),
            "reason": err["msg"],
        })
    return create_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Schema Validation Failure",
        detail="The inbound request payload violated strict schema v1.0 specifications.",
        instance=str(request.url),
        invalid_params=invalid_params,
    )


async def state_transition_exception_handler(request: Request, exc: StateTransitionError) -> JSONResponse:
    """Handle illegal FSM transitions with HTTP 400 Bad Request."""
    return create_problem_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Illegal State Transition",
        detail=str(exc),
        instance=str(request.url),
    )


async def concurrency_exception_handler(request: Request, exc: ConcurrencyError) -> JSONResponse:
    """Handle OCC version collision with HTTP 409 Conflict."""
    return create_problem_response(
        status_code=status.HTTP_409_CONFLICT,
        title="Optimistic Concurrency Conflict",
        detail=str(exc),
        instance=str(request.url),
    )


async def security_anomaly_exception_handler(request: Request, exc: SecurityAnomalyError) -> JSONResponse:
    """Handle token tampering or permission violations with HTTP 403 Forbidden."""
    return create_problem_response(
        status_code=status.HTTP_403_FORBIDDEN,
        title="Security Boundary Anomaly",
        detail=str(exc),
        instance=str(request.url),
    )


async def token_expired_exception_handler(request: Request, exc: TokenExpiredError) -> JSONResponse:
    """Handle token expiry with HTTP 401 Unauthorized."""
    return create_problem_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        title="Authentication Token Expired",
        detail=str(exc),
        instance=str(request.url),
    )


async def policy_violation_exception_handler(request: Request, exc: PolicyViolationError) -> JSONResponse:
    """Handle GC Shakti policy breach with HTTP 422 Unprocessable Entity."""
    return create_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Governance Policy Violation",
        detail=str(exc),
        instance=str(request.url),
    )


async def value_error_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle application value errors with HTTP 400 Bad Request."""
    return create_problem_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Invalid Request Parameter",
        detail=str(exc),
        instance=str(request.url),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler ensuring zero unhandled 500 exceptions."""
    trace_id = f"err_{uuid.uuid4().hex[:12]}"
    return create_problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Controlled Internal Error Boundary",
        detail=f"An unhandled internal fault occurred. Trace ID: {trace_id}. Reason: {str(exc)}",
        instance=str(request.url),
    )
