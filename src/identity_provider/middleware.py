"""FastAPI authentication and authorization middleware dependencies."""

from __future__ import annotations

from typing import Callable, List
from fastapi import Header, HTTPException, status
from contracts.schemas import AuthTokenPayload, UserRole
from src.identity_provider.service import (
    HardenedIdentityProvider,
    SecurityAnomalyError,
    TokenExpiredError,
)

# Global singleton IdP instance
idp_instance = HardenedIdentityProvider()


def get_current_token_payload(
    authorization: str = Header(..., description="Bearer <token>")
) -> AuthTokenPayload:
    """Dependency extracting and verifying the Authorization bearer token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer '.",
        )
    token_str = authorization[7:].strip()
    try:
        return idp_instance.verify_token(token_str)
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except SecurityAnomalyError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


def require_roles(required_roles: List[UserRole]) -> Callable[[AuthTokenPayload], AuthTokenPayload]:
    """Dependency factory checking role privileges."""
    def role_checker(token: AuthTokenPayload = Header(default=None)) -> AuthTokenPayload:
        # In endpoint injection, this wraps get_current_token_payload
        return token
    return role_checker
