"""Data models for Hardened Identity Provider Subsystem."""

from __future__ import annotations

import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from contracts.schemas import UserRole, SchemaVersion


class UserEntity(BaseModel):
    """User account entity registered within the Identity Provider."""
    schema_version: SchemaVersion = SchemaVersion.V1_0
    user_id: str = Field(..., min_length=3)
    username: str = Field(..., min_length=3)
    role: UserRole
    scopes: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class SessionRecord(BaseModel):
    """Active or historical session record."""
    session_id: str
    user_id: str
    role: UserRole
    issued_at: datetime.datetime
    expires_at: datetime.datetime
    revoked: bool = False
