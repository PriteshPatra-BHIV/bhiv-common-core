"""Bucket: Evidence & Immutable Audit Storage connector."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


class BucketStorageConnector:
    """Connector for storing immutable evaluation evidence and test logs in Bucket."""

    _storage: Dict[str, str] = {}

    @classmethod
    def store_evidence(cls, key: str, data: Any) -> str:
        """Store evidence payload in Bucket and return immutable URI."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        uri = f"bucket://bhiv-immutable-evidence/{key}-{content_hash[:16]}.json"
        cls._storage[uri] = serialized
        return uri

    @classmethod
    def fetch_evidence(cls, uri: str) -> str:
        """Retrieve evidence payload from Bucket."""
        if uri not in cls._storage:
            raise KeyError(f"Evidence URI {uri} not found in Bucket.")
        return cls._storage[uri]
