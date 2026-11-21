"""Hardened Identity Provider Service.
Enforces cryptographic token generation, tampering detection, revocation, and RBAC/ABAC.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
from typing import Dict, List, Optional, Set

from contracts.schemas import AuthTokenPayload, UserRole, SchemaVersion
from src.identity_provider.models import UserEntity, SessionRecord


class SecurityAnomalyError(Exception):
    """Raised when token tampering, signature failure, or security boundary violation occurs."""
    pass


class TokenExpiredError(Exception):
    """Raised when an expired authentication token is presented."""
    pass


class HardenedIdentityProvider:
    """Production Identity Provider enforcing zero-trust authorization."""

    def __init__(self, signing_secret: str = "BHIV_PRODUCTION_SETU_IDP_SECRET_KEY_v6.0") -> None:
        self._secret = signing_secret.encode("utf-8")
        self._users: Dict[str, UserEntity] = {}
        self._revoked_tokens: Set[str] = set()
        self._sessions: Dict[str, SessionRecord] = {}

        # Seed standard system users
        self._seed_default_users()

    def _seed_default_users(self) -> None:
        users = [
            UserEntity(
                user_id="usr_admin_01",
                username="admin_gov",
                role=UserRole.ADMIN,
                scopes=["*"],
            ),
            UserEntity(
                user_id="usr_reviewer_01",
                username="lead_reviewer_shakti",
                role=UserRole.REVIEWER,
                scopes=["reviews:read", "reviews:write", "tasks:assign"],
            ),
            UserEntity(
                user_id="usr_candidate_pritesh",
                username="pritesh_patra",
                role=UserRole.CANDIDATE,
                scopes=["tasks:read", "submissions:write"],
            ),
            UserEntity(
                user_id="usr_governance_01",
                username="gc_shakti_officer",
                role=UserRole.GOVERNANCE_OFFICER,
                scopes=["governance:audit", "ledger:verify"],
            ),
        ]
        for u in users:
            self._users[u.user_id] = u

    def register_user(self, user: UserEntity) -> None:
        self._users[user.user_id] = user

    def get_user(self, user_id: str) -> Optional[UserEntity]:
        return self._users.get(user_id)

    def _generate_signature(self, raw_data: bytes) -> str:
        return hmac.new(self._secret, raw_data, hashlib.sha256).hexdigest()

    def issue_token(
        self,
        user_id: str,
        role: UserRole,
        scopes: Optional[List[str]] = None,
        ttl_seconds: int = 3600,
        fixed_now: Optional[datetime.datetime] = None,
    ) -> AuthTokenPayload:
        """Issue cryptographically signed tamper-evident bearer token."""
        now = fixed_now or datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)

        payload_dict = {
            "sub": user_id,
            "role": role.value,
            "scopes": scopes or [],
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        serialized = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(serialized).decode("utf-8")
        signature = self._generate_signature(serialized)
        token_str = f"bhiv.{b64_payload}.{signature}"

        token_payload = AuthTokenPayload(
            schema_version=SchemaVersion.V1_0,
            token=token_str,
            user_id=user_id,
            role=role,
            scopes=scopes or [],
            issued_at=now,
            expires_at=expires_at,
        )

        session_id = f"sess_{signature[:12]}"
        self._sessions[session_id] = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            role=role,
            issued_at=now,
            expires_at=expires_at,
        )

        return token_payload

    def verify_token(
        self,
        token_str: str,
        current_time: Optional[datetime.datetime] = None,
    ) -> AuthTokenPayload:
        """Verify token authenticity, signature integrity, and active status."""
        if token_str in self._revoked_tokens:
            raise SecurityAnomalyError("Token has been revoked.")

        parts = token_str.split(".")
        if len(parts) != 3 or parts[0] != "bhiv":
            raise SecurityAnomalyError("Malformed token structure; expected 'bhiv.<payload>.<sig>'")

        b64_payload, signature = parts[1], parts[2]
        try:
            serialized = base64.urlsafe_b64decode(b64_payload.encode("utf-8"))
            data = json.loads(serialized.decode("utf-8"))
        except Exception as e:
            raise SecurityAnomalyError(f"Token decoding error: {str(e)}")

        expected_sig = self._generate_signature(serialized)
        if not hmac.compare_digest(signature, expected_sig):
            raise SecurityAnomalyError("Cryptographic signature mismatch: token has been tampered with.")

        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        exp_timestamp = data.get("exp", 0)
        if exp_timestamp < int(now.timestamp()):
            raise TokenExpiredError(f"Token expired at {exp_timestamp}; current time is {int(now.timestamp())}.")

        user_id = data.get("sub", "")
        role_str = data.get("role", "")
        scopes = data.get("scopes", [])
        iat_timestamp = data.get("iat", 0)

        return AuthTokenPayload(
            schema_version=SchemaVersion.V1_0,
            token=token_str,
            user_id=user_id,
            role=UserRole(role_str),
            scopes=scopes,
            issued_at=datetime.datetime.fromtimestamp(iat_timestamp, tz=datetime.timezone.utc),
            expires_at=datetime.datetime.fromtimestamp(exp_timestamp, tz=datetime.timezone.utc),
        )

    def revoke_token(self, token_str: str) -> None:
        """Add token to revocation registry."""
        self._revoked_tokens.add(token_str)

    def enforce_role(self, token_payload: AuthTokenPayload, required_roles: List[UserRole]) -> None:
        """Check role membership; ADMIN bypasses specific role restrictions."""
        if token_payload.role == UserRole.ADMIN:
            return
        if token_payload.role not in required_roles:
            raise SecurityAnomalyError(
                f"Unauthorized role: user has {token_payload.role.value}, "
                f"required one of {[r.value for r in required_roles]}."
            )
