"""Reference Code Packet: Routing, API Endpoints, and Security Middleware."""

from src.api.routes import router
from src.identity_provider.service import HardenedIdentityProvider
from src.identity_provider.middleware import get_current_token_payload, require_roles
from src.api.error_handlers import (
    create_problem_response,
    validation_exception_handler,
    concurrency_exception_handler,
    security_anomaly_exception_handler,
)

__all__ = [
    "router",
    "HardenedIdentityProvider",
    "get_current_token_payload",
    "require_roles",
    "create_problem_response",
    "validation_exception_handler",
    "concurrency_exception_handler",
    "security_anomaly_exception_handler",
]
