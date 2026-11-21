"""Tier 1 Unit Tests: Hardened Identity Provider token cryptography and security boundaries."""

from __future__ import annotations

import datetime
import pytest
from contracts.schemas import UserRole
from src.identity_provider.service import (
    HardenedIdentityProvider,
    SecurityAnomalyError,
    TokenExpiredError,
)


def test_token_issuance_and_verification() -> None:
    """Verify valid token issuance and verification round-trip."""
    idp = HardenedIdentityProvider(signing_secret="TEST_SECRET_KEY_123")
    token_payload = idp.issue_token(
        user_id="usr_pritesh",
        role=UserRole.CANDIDATE,
        scopes=["tasks:read", "submissions:write"],
        ttl_seconds=1800,
    )

    verified = idp.verify_token(token_payload.token)
    assert verified.user_id == "usr_pritesh"
    assert verified.role == UserRole.CANDIDATE
    assert "submissions:write" in verified.scopes


def test_token_tampering_detection() -> None:
    """Verify that tampering with token payload or signature raises SecurityAnomalyError."""
    idp = HardenedIdentityProvider(signing_secret="TEST_SECRET_KEY_123")
    token_payload = idp.issue_token(user_id="usr_test", role=UserRole.REVIEWER)

    parts = token_payload.token.split(".")
    # Tamper with the signature
    tampered_sig = parts[2][:-4] + "ffff"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(SecurityAnomalyError, match="Cryptographic signature mismatch"):
        idp.verify_token(tampered_token)


def test_token_expiration_enforcement() -> None:
    """Verify that expired tokens are immediately rejected."""
    idp = HardenedIdentityProvider(signing_secret="TEST_SECRET_KEY_123")
    past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=500)
    token_payload = idp.issue_token(
        user_id="usr_expired",
        role=UserRole.AUDITOR,
        ttl_seconds=100,
        fixed_now=past_time,
    )

    with pytest.raises(TokenExpiredError):
        idp.verify_token(token_payload.token)


def test_token_revocation() -> None:
    """Verify that revoked tokens cannot be used."""
    idp = HardenedIdentityProvider(signing_secret="TEST_SECRET_KEY_123")
    token_payload = idp.issue_token(user_id="usr_revoked", role=UserRole.CANDIDATE)

    # Token works initially
    assert idp.verify_token(token_payload.token).user_id == "usr_revoked"

    # Revoke token
    idp.revoke_token(token_payload.token)

    with pytest.raises(SecurityAnomalyError, match="revoked"):
        idp.verify_token(token_payload.token)
