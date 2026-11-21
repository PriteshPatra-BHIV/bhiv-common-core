"""Global pytest fixtures and test configuration for BHIV Enterprise Core.
Provides a fast, sandbox-compliant synchronous client and test fixtures.
"""

from __future__ import annotations

import datetime
import json
import urllib.parse
from typing import Any, Dict, Optional
import pytest

from pydantic import ValidationError
from contracts.schemas import (
    DifficultyLevel,
    PriorityLevel,
    TaskSpec,
    UserRole,
    SchemaVersion,
    ReviewSubmissionPayload,
    EvaluationSubmissionPayload,
    NextTaskAssignmentRequest,
)
from src.api.app import app
from src.api.routes import (
    create_task,
    get_task,
    submit_review,
    start_review,
    evaluate_submission,
    assign_next_task,
    get_ledger_events,
    get_ledger_state_hash,
    get_saarthi_metrics,
    ingest_legacy_task,
    get_current_token,
    core_service,
    idp_service,
)
from src.identity_provider.service import (
    HardenedIdentityProvider,
    SecurityAnomalyError,
    TokenExpiredError,
)
from src.enterprise_core.models import ConcurrencyError
from src.enterprise_core.state_machine import StateTransitionError
from src.integrations.gc_shakti import PolicyViolationError


class SyncResponse:
    """Mock HTTP Response object mimicking requests/httpx Response."""

    def __init__(self, status_code: int, data: Any) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> Any:
        if isinstance(self._data, (dict, list)):
            return self._data
        return json.loads(self._data)

    @property
    def text(self) -> str:
        if isinstance(self._data, str):
            return self._data
        return json.dumps(self._data)


class FastAPISyncClient:
    """Synchronous test client executing routes in-process without network/anyio blocking."""

    def __init__(self) -> None:
        self.core = core_service
        self.idp = idp_service

    def _extract_token(self, headers: Optional[Dict[str, str]]) -> Any:
        auth_header = (headers or {}).get("Authorization")
        if not auth_header:
            return None
        return get_current_token(auth_header)

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> SyncResponse:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            token = self._extract_token(headers)
            if not token:
                return SyncResponse(401, {"detail": "Missing Authorization header."})

            if path == "/api/v1/ledger/state-hash":
                res = get_ledger_state_hash(token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/ledger/events":
                res = get_ledger_events(token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/saarthi/metrics":
                res = get_saarthi_metrics(token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path.startswith("/api/v1/tasks/"):
                task_id = path.split("/")[-1]
                res = get_task(task_id=task_id, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            return SyncResponse(404, {"detail": f"Path {path} not found"})

        except SecurityAnomalyError as e:
            return SyncResponse(403, {"title": "Security Boundary Anomaly", "status": 403, "detail": str(e)})
        except TokenExpiredError as e:
            return SyncResponse(401, {"title": "Authentication Token Expired", "status": 401, "detail": str(e)})
        except Exception as e:
            return SyncResponse(500, {"title": "Internal Fault", "status": 500, "detail": str(e)})

    def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> SyncResponse:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            token = self._extract_token(headers)

            if path == "/api/v1/tasks":
                if not token:
                    return SyncResponse(401, {"detail": "Missing or malformed Authorization header."})
                if not json or "task_id" not in json:
                    return SyncResponse(
                        422,
                        {
                            "title": "Schema Validation Failure",
                            "status": 422,
                            "invalid_params": [{"name": "body", "reason": "Missing mandatory task_id"}],
                        },
                    )
                spec = TaskSpec(**json)
                res = create_task(spec=spec, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/submissions":
                if not token:
                    return SyncResponse(401, {"detail": "Missing Authorization header."})
                expected_v = int(query.get("expected_version", [1])[0])
                sub = ReviewSubmissionPayload(**(json or {}))
                res = submit_review(submission=sub, expected_version=expected_v, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/reviews/start":
                if not token:
                    return SyncResponse(401, {"detail": "Missing Authorization header."})
                t_id = query.get("task_id", [""])[0]
                exp_v = int(query.get("expected_version", [1])[0])
                res = start_review(task_id=t_id, expected_version=exp_v, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/reviews/evaluate":
                if not token:
                    return SyncResponse(401, {"detail": "Missing Authorization header."})
                exp_v = int(query.get("expected_version", [1])[0])
                ev = EvaluationSubmissionPayload(**(json or {}))
                res = evaluate_submission(evaluation=ev, expected_version=exp_v, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/reviews/assign-next":
                if not token:
                    return SyncResponse(401, {"detail": "Missing Authorization header."})
                exp_v = int(query.get("expected_version", [1])[0])
                req = NextTaskAssignmentRequest(**(json or {}))
                res = assign_next_task(request=req, expected_version=exp_v, token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            elif path == "/api/v1/legacy/ingest":
                if not token:
                    return SyncResponse(401, {"detail": "Missing Authorization header."})
                res = ingest_legacy_task(payload=(json or {}), token=token)
                return SyncResponse(200, res.model_dump(mode="json"))

            return SyncResponse(404, {"detail": f"Path {path} not found"})

        except ValidationError as e:
            return SyncResponse(
                422,
                {
                    "title": "Schema Validation Failure",
                    "status": 422,
                    "invalid_params": [{"name": "validation", "reason": str(e)}],
                },
            )
        except SecurityAnomalyError as e:
            return SyncResponse(403, {"title": "Security Boundary Anomaly", "status": 403, "detail": str(e)})
        except TokenExpiredError as e:
            return SyncResponse(401, {"title": "Authentication Token Expired", "status": 401, "detail": str(e)})
        except StateTransitionError as e:
            return SyncResponse(400, {"title": "Illegal State Transition", "status": 400, "detail": str(e)})
        except ConcurrencyError as e:
            return SyncResponse(409, {"title": "Optimistic Concurrency Conflict", "status": 409, "detail": str(e)})
        except PolicyViolationError as e:
            return SyncResponse(422, {"title": "Governance Policy Violation", "status": 422, "detail": str(e)})
        except Exception as e:
            return SyncResponse(500, {"title": "Controlled Internal Error Boundary", "status": 500, "detail": str(e)})


@pytest.fixture
def client() -> FastAPISyncClient:
    """Sandbox-safe synchronous client for HTTP tests."""
    return FastAPISyncClient()


@pytest.fixture
def idp() -> HardenedIdentityProvider:
    """Reference to system IdP service."""
    return idp_service


@pytest.fixture
def core_service_fixture() -> EnterpriseCoreService:
    """Reference to core service."""
    return core_service


@pytest.fixture
def admin_token(idp: HardenedIdentityProvider) -> str:
    payload = idp.issue_token(user_id="usr_admin_01", role=UserRole.ADMIN)
    return payload.token


@pytest.fixture
def reviewer_token(idp: HardenedIdentityProvider) -> str:
    payload = idp.issue_token(
        user_id="usr_reviewer_01",
        role=UserRole.REVIEWER,
        scopes=["reviews:write", "tasks:assign"],
    )
    return payload.token


@pytest.fixture
def candidate_token(idp: HardenedIdentityProvider) -> str:
    payload = idp.issue_token(
        user_id="usr_candidate_pritesh",
        role=UserRole.CANDIDATE,
        scopes=["submissions:write"],
    )
    return payload.token


@pytest.fixture
def sample_task_spec() -> TaskSpec:
    return TaskSpec(
        schema_version=SchemaVersion.V1_0,
        task_id="T-GOV-002",
        title="BHIV Advancement Milestone: Advanced Enterprise Core & Identity Provider Hardening",
        department="AI ML",
        priority=PriorityLevel.MEDIUM,
        calibrated_duration_hours=35,
        difficulty_level=DifficultyLevel.BEGINNER,
        phases=[
            "Phase 1 Day 1: Problem Analysis, Environment Setup & Contract Specifications",
            "Phase 2 Day 2: Data Models, Inbound Validation Gateways & Initial Unit Tests",
            "Phase 3 Day 3: Core Work Package 2 Implementation & Logic Hardening",
            "Phase 4 Day 4: Subsystem Integration, Replay Ledger & Backward Compatibility",
            "Phase 5 Day 5: Negative Testing, Security Boundaries & Error Recovery",
            "Phase 6 Day 6: Regression Test Suite & 50-Run Determinism Benchmark",
            "Phase 7 Day 7: Documentation, Self-Audit REVIEW_PACKET.md & Packaging",
        ],
        acceptance_criteria=[
            "1-Minute Cognition for engineering managers",
            "Zero-Context-Switch Assignment",
            "Canonical Depth: zero placeholder IDs",
            "100% Test Pass Rate across 5-Tier Matrix",
            "Zero unpinned >= dependencies in requirements.txt",
            "50 consecutive runs produce identical SHA-256 state hashes",
            "Zero unhandled 500 exceptions on malformed or invalid inputs",
        ],
        canonical_spec_body=(
            "Transform BHIV Enterprise Operating System Common Core into a government-grade "
            "operational review and engineering platform adhering to SETU OS Architecture v6.0."
        ),
    )
