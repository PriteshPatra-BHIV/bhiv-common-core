"""FastAPI Application Entrypoint for BHIV Enterprise Core Platform."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from contracts.schemas import SchemaVersion
from src.api.error_handlers import (
    concurrency_exception_handler,
    generic_exception_handler,
    policy_violation_exception_handler,
    security_anomaly_exception_handler,
    state_transition_exception_handler,
    token_expired_exception_handler,
    validation_exception_handler,
    value_error_exception_handler,
)
from src.api.routes import router
from src.enterprise_core.models import ConcurrencyError
from src.enterprise_core.state_machine import StateTransitionError
from src.identity_provider.service import SecurityAnomalyError, TokenExpiredError
from src.integrations.gc_shakti import PolicyViolationError


def create_app() -> FastAPI:
    """Initialize and configure the production BHIV Enterprise Core FastAPI application."""
    app = FastAPI(
        title="BHIV Enterprise Operating System Common Core",
        version=SchemaVersion.V1_0.value,
        description=(
            "Government-grade operational review and engineering execution platform. "
            "Enforces strict schema validation (v1.0), deterministic state machine transitions, "
            "hardened identity boundaries, and cryptographic replay audit logging."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register error boundaries
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StateTransitionError, state_transition_exception_handler)
    app.add_exception_handler(ConcurrencyError, concurrency_exception_handler)
    app.add_exception_handler(SecurityAnomalyError, security_anomaly_exception_handler)
    app.add_exception_handler(TokenExpiredError, token_expired_exception_handler)
    app.add_exception_handler(PolicyViolationError, policy_violation_exception_handler)
    app.add_exception_handler(ValueError, value_error_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Mount API routes
    app.include_router(router, prefix="/api/v1")

    return app


app = create_app()
