# pyright: reportArgumentType=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false, reportRedeclaration=false
from __future__ import annotations

import ast
import asyncio
import base64
import copy
from collections import UserDict
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
import inspect
import hashlib
import hmac
import json
import pickle
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest  # type: ignore[import-not-found]
from pydantic import ValidationError  # type: ignore[import-not-found]
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]
    async_sessionmaker,
    create_async_engine,
)
from starlette.requests import Request

from app.api.deps.authorization import (
    authorization_http_error,
    get_authorization_actor,
    get_authorization_service,
    get_prepared_authorization_service,
)
from app.api.deps.api_controls import (
    enforce_admin_mutation_rate_limit,
    enforce_authorization_read_rate_limit,
)
from app.api.deps.auth import get_auth_verification_result
from app.core.api_controls import StructuredHTTPException
from app.core.config import Settings, get_settings
from app.core.hashing import canonical_json_hash
from app.db.session import get_db_session
from app.main import create_app
from app.modules.projects.repository import ProjectRepository
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ActorService, ResolvedActor
from app.modules.actors.service_identities import SERVICE_IDENTITIES, ServiceIdentity
from app.modules.authorization import catalogue as authorization_catalogue
from app.modules.authorization import kernel as authorization_kernel
from app.modules.authorization import router as authorization_router
from app.modules.authorization.admin_schemas import AdminRoleGrantRevokeBody
from app.modules.authorization.lifecycle_schemas import (
    ActorLifecycleBody,
    ActorLifecycleMutationResponse,
    IdentityLinkLifecycleMutationResponse,
)
from app.modules.authorization.lifecycle_service import (
    ActorLifecycleConflict,
    ActorLifecycleService,
    IdentityLinkLifecycleConflict,
    IdentityLinkLifecycleService,
)
from app.modules.authorization.models import (
    AdminRoleGrant,
    ProjectRoleGrant,
    ProjectRoleQualificationSnapshot,
)
from project_create_fixtures import seed_authorized_project
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec,
    InvalidPaginationCursor,
    authorization_read_query_digest,
)
from app.modules.authorization.read_service import (
    ActorAuthorizationContextReadService,
    ProjectRoleReadService,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    ACTION_DEFINITIONS,
    ACTION_IDS,
    HISTORICAL_PERMISSION_IDS,
    NEW_PERMISSION_IDS,
    PERMISSION_IDS,
    ActionAvailability,
    ActionDefinition,
    ActionId,
    ActionOwner,
    PermissionId,
    SERVICE_ACTIONS_BY_IDENTITY,
    _index_actions,
    _index_service_actions,
    resolve_executable_action,
)
from app.modules.authorization.schemas import (
    ActorIdentityLinkReactivateRequest,
    ActorIdentityLinkRevokeRequest,
    ActorProfileDeactivateRequest,
    ActorProfileReactivateRequest,
    ActorProfileSuspendRequest,
    AdminRole,
    AdminRoleGrantIssueRequest,
    AdminRoleGrantRevokeRequest,
    AdminScope,
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityOperation,
    AuthorityResourceType,
    AuthorityResponseReference,
    ClaimedReservation,
    InvalidAuthorityClaimError,
    MismatchedReservation,
    PendingAuthorityReservationError,
    ProjectRole,
    ProjectRoleQualificationEvidence,
    ProjectRoleQualificationSnapshotInput,
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    QualificationAvailabilitySnapshot,
    QualificationAvailability,
    QualificationUnavailableReason,
    ReplayedReservation,
    ServiceActorCreateRequest,
    derive_reason_digest,
    derive_service_identity_digest,
    parse_authority_request,
)
from app.modules.authorization.service import AuthorityMutationService
from app.modules.authorization.project_role_service import (
    _constraint_name,
    ProjectRoleGrantMutationService,
    project_role_issue_lock_key,
)
from app.modules.authorization.project_role_schemas import (
    ProjectRoleGrantIssueBody,
    ProjectRoleGrantMutationResponse,
    ProjectRoleGrantRevokeBody,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.admin_service import (
    AdminRoleGrantService,
    BootstrapAlreadyCompleted,
    BootstrapTargetIneligible,
    LastAccessAdministratorConflict,
)
from app.modules.authorization.policy import ADMIN_ROLE_PERMISSIONS, ADMIN_ROLE_SCOPES
from app.modules.authorization.runtime import (
    ActorAdminRoleGrantHistoryResourceContext,
    ActorAuthorizationContextResourceContext,
    ActorIdentityLinkAdminReadResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
    ActorKind,
    ActorProfileAdminReadResourceContext,
    ActorProfileLifecycleResourceContext,
    ActorSelfResourceContext,
    ActorStatus,
    ArtifactVerificationJobResourceContext,
    AdminRoleDefinitionsResourceContext,
    AdminRoleGrantCollectionResourceContext,
    AdminRoleGrantIssueResourceContext,
    AdminRoleGrantResourceContext,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationDenialCode,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    GuideSourceIngestResourceContext,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    MatchedAuthorityKind,
    PermissionCatalogueResourceContext,
    ProjectContributorCandidateCollectionResourceContext,
    ProjectDiagnosticReadResourceContext,
    PROJECT_MUTATION_RESOURCE_BY_ACTION,
    ProjectCreateResourceContext,
    ProjectGuideActivationResourceContext,
    ProjectGuideMutationResourceContext,
    ProjectGuideSourceSnapshotMutationResourceContext,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectPostSubmitCheckerPolicyMutationResourceContext,
    ProjectReviewPolicyMutationResourceContext,
    ProjectRevisionPolicyMutationResourceContext,
    ProjectSetupServiceCustodyContext,
    ProjectSetupRunMutationResourceContext,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    ProjectPolicyReadResourceContext,
    ProjectActiveGuideReadResourceContext,
    ProjectReadResourceContext,
    ProjectRoleGrantCollectionResourceContext,
    ProjectRoleGrantIssueResourceContext,
    ProjectRoleGrantReadResourceContext,
    ProjectRoleGrantRevokeResourceContext,
    ServiceActorProvisionResourceContext,
    ServiceAuthorizationContext,
    SystemResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.service_actor_service import (
    ServiceActorConflict,
    ServiceActorProvisioningService,
    ServiceActorProvisioningUnavailable,
)

DIGEST = "sha256:" + "a" * 64


def _project_role_qualification() -> dict[str, object]:
    return {
        "skills_snapshot": {
            "availability": QualificationAvailability.AVAILABLE,
            "reference_ids": ["skill:opaque"],
            "unavailable_reason": None,
        },
        "reputation_snapshot": {
            "availability": QualificationAvailability.UNAVAILABLE,
            "reference_ids": [],
            "unavailable_reason": QualificationUnavailableReason.NO_RECORD,
        },
        "prior_project_work_refs": [],
        "external_expertise_refs": [],
    }


def test_project_role_issue_advisory_key_contract_is_frozen_and_separated() -> None:
    actor = UUID("00000000-0000-0000-0000-000000000001")
    project = UUID("00000000-0000-0000-0000-000000000002")
    assert project_role_issue_lock_key(actor, project, "submitter") == -7801444014257588548
    values = {
        project_role_issue_lock_key(actor, project, role)
        for role in ("submitter", "reviewer", "adjudicator")
    }
    assert len(values) == 3
    assert all(-(2**63) <= value < 2**63 for value in values)
    assert project_role_issue_lock_key(actor, project, "submitter") != project_role_issue_lock_key(
        project, actor, "submitter"
    )
    original = SimpleNamespace(constraint_name="uq_project_role_grants_active_exact_role")
    error = IntegrityError("insert", {}, original)
    assert _constraint_name(error) == "uq_project_role_grants_active_exact_role"


@pytest.mark.asyncio
async def test_project_role_issue_crossed_principals_use_one_lexical_lock_order() -> None:
    low = UUID("00000000-0000-0000-0000-000000000001")
    high = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    low_link, high_link = uuid4(), uuid4()

    class RecordingSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, UUID]] = []

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            values = set(statement.compile().params.values())
            actor = low if str(low) in values else high
            if entity is ActorProfile:
                self.calls.append(("profile", actor))
                return SimpleNamespace(id=str(actor), actor_kind="human", status="active")
            self.calls.append(("link", actor))
            link_id = low_link if actor == low else high_link
            return SimpleNamespace(id=str(link_id), actor_profile_id=str(actor))

    expected = [
        ("profile", low),
        ("link", low),
        ("profile", high),
        ("link", high),
    ]
    for caller, caller_link, target in (
        (low, low_link, high),
        (high, high_link, low),
    ):
        session = RecordingSession()
        repository = AdminAuthorizationRepository(session)  # type: ignore[arg-type]
        locked_caller, target_eligible = await repository.lock_project_role_issue_principals(
            caller_actor_profile_id=caller,
            caller_identity_link_id=caller_link,
            target_actor_profile_id=target,
        )
        assert locked_caller is not None
        assert target_eligible is True
        assert session.calls == expected


def test_project_role_public_reason_and_qualification_contract_is_strict() -> None:
    payload = {
        "target_actor_profile_id": str(uuid4()),
        "role": "submitter",
        "qualification": _project_role_qualification(),
        "reason": "Bounded authority assignment",
    }
    assert (
        ProjectRoleGrantIssueBody.model_validate_json(json.dumps(payload)).role
        is ProjectRole.SUBMITTER
    )
    assert ProjectRoleGrantRevokeBody.model_validate({"reason": "Bounded removal"}).reason == (
        "Bounded removal"
    )
    for reason in (" padded", "padded ", "control\x00", "é" * 251):
        with pytest.raises(ValidationError):
            ProjectRoleGrantIssueBody.model_validate(payload | {"reason": reason})


def test_project_role_invalidation_projection_is_closed_per_role() -> None:
    project_id = uuid4()
    mappings = {
        ProjectRole.SUBMITTER: "auth13_assignment",
        ProjectRole.REVIEWER: "rev_reviewer_obligation",
        ProjectRole.ADJUDICATOR: "none",
    }
    for role, obligation in mappings.items():
        context = AuthorityInvalidationContext(
            event_id=uuid4(),
            request_id=uuid4(),
            correlation_id=uuid4(),
            target_ref_kind=AuthorityResourceType.PROJECT_ROLE_GRANT,
            target_ref_id=uuid4(),
            project_role=role,
            future_obligation=obligation,
        )
        projection = {
            "role": role.value,
            "scope_type": "project",
            "scope_id": str(project_id),
            "future_obligation": obligation,
        }
        event_id = uuid4()
        event = AuthorityAuditEventInput(
            event_id=event_id,
            event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            entity_type="authority_invalidation",
            entity_id=str(event_id),
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(uuid4()),
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
            project_id=str(project_id),
            resource_type="actor_profile",
            resource_id=str(uuid4()),
            target_ref_kind="project_role_grant",
            target_ref_id=str(context.target_ref_id),
            reason="authority_state_changed",
            idempotency_reference=uuid4(),
            invalidation_cause_event_id=uuid4(),
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=str(uuid4()),
            before_facts={"effective": True, **projection},
            after_facts={"effective": False, **projection},
        )
        assert event.after_facts["future_obligation"] == obligation
    with pytest.raises(ValidationError):
        AuthorityInvalidationContext(
            event_id=uuid4(),
            request_id=uuid4(),
            correlation_id=uuid4(),
            project_role=ProjectRole.SUBMITTER,
            future_obligation="none",
        )


def test_authorization_read_cursor_round_trip_and_query_binding() -> None:
    codec = AuthorizationReadCursorCodec(bytes(range(32)))
    project_id = UUID("00000000-0000-4000-8000-000000000001")
    resource_id = UUID("00000000-0000-4000-8000-000000000002")
    boundary = datetime(2026, 7, 22, 1, 2, 3, 456789, tzinfo=UTC)
    digest = authorization_read_query_digest(
        action_id=ActionId.PROJECT_ROLE_GRANT_LIST,
        project_id=project_id,
        status="active",
        role=ProjectRole.REVIEWER,
        limit=50,
    )

    cursor = codec.encode(query_digest=digest, timestamp=boundary, resource_id=resource_id)

    assert len(cursor) <= 512
    assert codec.decode(cursor, query_digest=digest) == (boundary, resource_id)
    replay_digest = authorization_read_query_digest(
        action_id=ActionId.PROJECT_ROLE_GRANT_LIST,
        project_id=project_id,
        status="revoked",
        role=ProjectRole.REVIEWER,
        limit=50,
    )
    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        codec.decode(cursor, query_digest=replay_digest)


@pytest.mark.parametrize(
    "value",
    ["", "=", "a===", "*", "a" * 513],
)
def test_authorization_read_cursor_rejects_malformed_encoding(value: str) -> None:
    codec = AuthorizationReadCursorCodec(bytes(range(32)))
    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        codec.decode(value, query_digest=DIGEST)


def test_authorization_read_cursor_rejects_tampering_and_wrong_key() -> None:
    digest = authorization_read_query_digest(
        action_id=ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        project_id=UUID("00000000-0000-4000-8000-000000000001"),
        limit=10,
    )
    codec = AuthorizationReadCursorCodec(bytes(range(32)))
    cursor = codec.encode(
        query_digest=digest,
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        resource_id=UUID("00000000-0000-4000-8000-000000000002"),
    )
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")

    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        codec.decode(tampered, query_digest=digest)
    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(reversed(range(32)))).decode(
            cursor,
            query_digest=digest,
        )


def _signed_cursor_envelope(envelope: dict, *, secret: bytes = bytes(range(32))) -> str:
    payload = envelope["p"]
    payload_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    envelope["s"] = (
        base64.urlsafe_b64encode(hmac.new(secret, payload_bytes, hashlib.sha256).digest())
        .decode()
        .rstrip("=")
    )
    return (
        base64.urlsafe_b64encode(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )


@pytest.mark.parametrize(
    "payload_update,envelope_update",
    [
        ({"v": 2}, {}),
        ({"v": "1"}, {}),
        ({"extra": True}, {}),
        ({"ts": "2026-07-22T00:00:00Z"}, {}),
        ({"ts": "2026-07-22T00:00:00.000000+00:00"}, {}),
        ({"id": "ABCDEF00-0000-4000-8000-000000000002"}, {}),
        ({"id": 2}, {}),
        ({}, {"extra": True}),
    ],
)
def test_authorization_read_cursor_rejects_strict_payload_variants(
    payload_update: dict,
    envelope_update: dict,
) -> None:
    payload = {
        "v": 1,
        "q": DIGEST,
        "ts": "2026-07-22T00:00:00.000000Z",
        "id": "00000000-0000-4000-8000-000000000002",
    }
    payload.update(payload_update)
    envelope = {"p": payload, "s": ""}
    envelope.update(envelope_update)
    cursor = _signed_cursor_envelope(envelope)

    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(range(32))).decode(
            cursor,
            query_digest=DIGEST,
        )


@pytest.mark.parametrize("missing_key", ["v", "q", "ts", "id"])
def test_authorization_read_cursor_rejects_missing_payload_keys(missing_key: str) -> None:
    payload = {
        "v": 1,
        "q": DIGEST,
        "ts": "2026-07-22T00:00:00.000000Z",
        "id": "00000000-0000-4000-8000-000000000002",
    }
    del payload[missing_key]
    cursor = _signed_cursor_envelope({"p": payload, "s": ""})

    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(range(32))).decode(
            cursor,
            query_digest=DIGEST,
        )


def test_authorization_read_cursor_rejects_oversized_decoded_value() -> None:
    value = base64.urlsafe_b64encode(b"{" + b" " * 383 + b"}").decode().rstrip("=")
    assert len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))) > 384
    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(range(32))).decode(
            value,
            query_digest=DIGEST,
        )


def test_authorization_read_cursor_rejects_missing_envelope_and_duplicate_keys() -> None:
    missing_signature = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "p": {
                        "v": 1,
                        "q": DIGEST,
                        "ts": "2026-07-22T00:00:00.000000Z",
                        "id": "00000000-0000-4000-8000-000000000002",
                    }
                },
                separators=(",", ":"),
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    duplicate = base64.urlsafe_b64encode(b'{"p":{},"p":{},"s":"x"}').decode().rstrip("=")
    codec = AuthorizationReadCursorCodec(bytes(range(32)))
    for value in (missing_signature, duplicate):
        with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
            codec.decode(value, query_digest=DIGEST)


@pytest.mark.parametrize(
    "digest_kwargs",
    [
        {"action_id": ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST},
        {"project_id": UUID("00000000-0000-4000-8000-000000000099")},
        {"status": "revoked"},
        {"role": ProjectRole.ADJUDICATOR},
        {"limit": 51},
    ],
)
def test_authorization_read_cursor_rejects_cross_query_replay(
    digest_kwargs: dict,
) -> None:
    project_id = UUID("00000000-0000-4000-8000-000000000001")
    baseline = {
        "action_id": ActionId.PROJECT_ROLE_GRANT_LIST,
        "project_id": project_id,
        "status": "active",
        "role": ProjectRole.REVIEWER,
        "limit": 50,
    }
    digest = authorization_read_query_digest(**baseline)
    cursor = AuthorizationReadCursorCodec(bytes(range(32))).encode(
        query_digest=digest,
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        resource_id=UUID("00000000-0000-4000-8000-000000000002"),
    )
    baseline.update(digest_kwargs)

    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(range(32))).decode(
            cursor,
            query_digest=authorization_read_query_digest(**baseline),
        )


def test_authorization_read_cursor_rejects_cross_order_replay() -> None:
    project_id = UUID("00000000-0000-4000-8000-000000000001")
    alternate_order_digest = canonical_json_hash(
        {
            "action_id": ActionId.PROJECT_ROLE_GRANT_LIST.value,
            "limit": 50,
            "order": "timestamp_uuid_desc",
            "project_id": str(project_id),
            "role": None,
            "status": None,
        }
    )
    cursor = AuthorizationReadCursorCodec(bytes(range(32))).encode(
        query_digest=alternate_order_digest,
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        resource_id=UUID("00000000-0000-4000-8000-000000000002"),
    )
    canonical_digest = authorization_read_query_digest(
        action_id=ActionId.PROJECT_ROLE_GRANT_LIST,
        project_id=project_id,
        limit=50,
    )

    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        AuthorizationReadCursorCodec(bytes(range(32))).decode(
            cursor,
            query_digest=canonical_digest,
        )


@pytest.mark.asyncio
async def test_invalid_cursor_is_rejected_after_authorization_before_grant_sql() -> None:
    calls: list[str] = []

    class Authorization:
        async def require(self, *_args) -> SimpleNamespace:
            calls.append("authorization")
            return SimpleNamespace(allowed=True)

    class Grants:
        async def list_project_role_grants(self, **_kwargs):
            calls.append("grant_sql")
            raise AssertionError("grant SQL must not run")

    service = ProjectRoleReadService(
        Authorization(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        Grants(),  # type: ignore[arg-type]
        AuthorizationReadCursorCodec(bytes(range(32))),
    )
    with pytest.raises(InvalidPaginationCursor, match="invalid cursor"):
        await service.list_project_role_grants(
            project=SimpleNamespace(
                id="00000000-0000-4000-8000-000000000001",
                status="active",
            ),
            status=None,
            role=None,
            limit=50,
            cursor="forged",
        )
    assert calls == ["authorization"]


@pytest.mark.asyncio
async def test_candidate_service_cursor_uses_last_visible_equal_timestamp_boundary() -> None:
    created_at = datetime(2026, 7, 22, tzinfo=UTC)
    ids = [UUID(f"00000000-0000-4000-8000-{index:012d}") for index in range(1, 4)]
    observed: list[tuple[datetime, UUID] | None] = []

    class Authorization:
        async def require(self, *_args) -> SimpleNamespace:
            return SimpleNamespace(allowed=True)

    class Actors:
        async def list_contributor_candidates(self, *, cursor, **_kwargs):
            observed.append(cursor)
            start = 0 if cursor is None else ids.index(cursor[1]) + 1
            return [
                SimpleNamespace(id=str(value), display_name=None, created_at=created_at)
                for value in ids[start : start + 3]
            ]

    codec = AuthorizationReadCursorCodec(bytes(range(32)))
    service = ProjectRoleReadService(
        Authorization(),  # type: ignore[arg-type]
        Actors(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        codec,
    )
    project = SimpleNamespace(id=str(uuid4()), status="active")
    first = await service.list_contributor_candidates(
        project=project,
        caller_actor_profile_id=uuid4(),
        limit=2,
        cursor=None,
    )
    assert [item.actor_profile_id for item in first.items] == ids[:2]
    assert first.next_cursor is not None
    second = await service.list_contributor_candidates(
        project=project,
        caller_actor_profile_id=uuid4(),
        limit=2,
        cursor=first.next_cursor,
    )
    assert [item.actor_profile_id for item in second.items] == ids[2:]
    assert second.next_cursor is None
    assert observed == [None, (created_at, ids[1])]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 503])
@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/projects/{project_id}/role-grants",
        "/api/v1/projects/{project_id}",
        "/api/v1/actors/me/authorization-context?project_id={project_id}",
        "/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        "/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
        "/api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup",
    ),
)
async def test_authorization_read_rate_failure_precedes_project_lookup(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    path: str,
) -> None:
    app = create_app(Settings(environment="test"))
    lookups = 0

    consumptions = 0

    async def fail_rate_first() -> None:
        nonlocal consumptions
        consumptions += 1
        raise StructuredHTTPException(
            status_code=status_code,
            detail="rate gate failed",
            error_code=("rate_limit_exceeded" if status_code == 429 else "service_unavailable"),
            error_message="rate gate failed",
            retryable=True,
            headers=({"Retry-After": "1"} if status_code == 429 else None),
        )

    async def forbidden_project_lookup(*_args, **_kwargs):
        nonlocal lookups
        lookups += 1
        raise AssertionError("project lookup must not run")

    async def verified_human():
        return SimpleNamespace(token=SimpleNamespace(subject_kind="human"))

    app.dependency_overrides[enforce_authorization_read_rate_limit] = fail_rate_first
    app.dependency_overrides[get_auth_verification_result] = verified_human
    monkeypatch.setattr(ProjectRepository, "get_project", forbidden_project_lookup)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            path.format(project_id=uuid4(), guide_id=uuid4(), report_id=uuid4(), policy_id=uuid4()),
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == status_code
    if status_code == 429:
        assert response.headers["Retry-After"] == "1"
    else:
        assert response.json()["error"]["retryable"] is True
    assert consumptions == 1
    assert lookups == 0


@pytest.mark.asyncio
async def test_human_read_admission_conceals_every_nonhuman_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for subject_kind in ("service", "agent", "space"):
        app = create_app(Settings(environment="test"))
        consumptions = 0
        lookups = 0

        async def consume_once() -> None:
            nonlocal consumptions
            consumptions += 1

        async def verified_nonhuman():
            return SimpleNamespace(token=SimpleNamespace(subject_kind=subject_kind))

        async def forbidden_project_lookup(*_args, **_kwargs):
            nonlocal lookups
            lookups += 1
            raise AssertionError("project lookup must not run")

        app.dependency_overrides[enforce_authorization_read_rate_limit] = consume_once
        app.dependency_overrides[get_auth_verification_result] = verified_nonhuman
        monkeypatch.setattr(ProjectRepository, "get_project", forbidden_project_lookup)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            for path in (
                f"/api/v1/projects/{uuid4()}/role-grants",
                f"/api/v1/projects/{uuid4()}",
                f"/api/v1/actors/me/authorization-context?project_id={uuid4()}",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/setup-runs/latest",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/sufficiency-reports",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/sufficiency-reports/{uuid4()}",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/submission-artifact-policies",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/submission-artifact-policies/{uuid4()}",
                f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/post-submit-checker-policy/setup",
            ):
                response = await client.get(path)
                assert response.status_code == 404
                assert response.json()["error"]["code"] == (
                    "project_authorization_resource_not_found"
                )

        assert consumptions == 9
        assert lookups == 0


@pytest.mark.asyncio
async def test_diagnostic_authentication_failure_precedes_private_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(Settings(environment="test"))
    lookups = 0

    async def consume_once() -> None:
        return None

    async def invalid_bearer():
        raise StructuredHTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            error_code="invalid_authentication",
            error_message="Invalid authentication credentials",
        )

    async def forbidden_project_lookup(*_args, **_kwargs):
        nonlocal lookups
        lookups += 1
        raise AssertionError("project lookup must not run")

    app.dependency_overrides[enforce_authorization_read_rate_limit] = consume_once
    app.dependency_overrides[get_auth_verification_result] = invalid_bearer
    monkeypatch.setattr(ProjectRepository, "get_project", forbidden_project_lookup)
    project_id, guide_id = uuid4(), uuid4()
    paths = (
        f"/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{uuid4()}",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{uuid4()}",
        f"/api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        responses = [await client.get(path) for path in paths]
    assert [response.status_code for response in responses] == [401] * 6
    assert lookups == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            lambda project, _grant: f"/api/v1/projects/{project}/role-grants",
            lambda: {
                "target_actor_profile_id": str(uuid4()),
                "role": "submitter",
                "qualification": _project_role_qualification(),
                "reason": "Bounded assignment",
            },
        ),
        (
            lambda project, grant: f"/api/v1/projects/{project}/role-grants/{grant}/revoke",
            lambda: {"reason": "Bounded removal"},
        ),
    ],
)
async def test_project_role_mutation_rate_failure_precedes_private_work(
    monkeypatch: pytest.MonkeyPatch,
    path,
    payload,
) -> None:
    app = create_app(Settings(environment="test"))
    calls = 0

    async def fail_rate_first() -> None:
        nonlocal calls
        calls += 1
        raise StructuredHTTPException(
            status_code=503,
            detail="rate persistence unavailable",
            error_code="service_unavailable",
            error_message="rate persistence unavailable",
            retryable=True,
        )

    async def forbidden_project_lookup(*_args, **_kwargs):
        raise AssertionError("private mutation work must not run")

    app.dependency_overrides[enforce_admin_mutation_rate_limit] = fail_rate_first
    monkeypatch.setattr(ProjectRepository, "get_project", forbidden_project_lookup)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            path(uuid4(), uuid4()),
            headers={"Idempotency-Key": str(uuid4())},
            json=payload(),
        )
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True
    assert calls == 1


def _project_role_denial_decision(
    action_id: ActionId,
    resource_id: UUID,
    denial_code: AuthorizationDenialCode,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        decision_id=uuid4(),
        allowed=False,
        action_id=action_id,
        permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        resource_type="project_role_grant",
        resource_id=resource_id,
        resource_context_digest=DIGEST,
        denial_code=denial_code,
        matched_authority_kind=None,
        matched_grant_id=None,
        matched_scope_project_id=None,
        revalidated=False,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("invocation", ["http_route", "direct_route"])
@pytest.mark.parametrize(
    ("operation", "hidden_case", "denial_code", "expected_status", "expected_code", "message"),
    [
        (
            "issue",
            "valid_target_no_manager",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "missing_target_no_manager",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "inactive_target_no_manager",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "nonhuman_target_no_manager",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "valid_target_cross_project_manager",
            AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "missing_target_manager",
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "inactive_target_manager",
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "nonhuman_target_manager",
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "unauthorized_target_manager",
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "issue",
            "self_target_manager",
            AuthorizationDenialCode.SELF_GRANT_FORBIDDEN,
            403,
            "self_grant_forbidden",
            "Self grant is forbidden",
        ),
        (
            "revoke",
            "nonexistent_grant",
            AuthorizationDenialCode.GRANT_NOT_FOUND,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "revoke",
            "cross_project_grant",
            AuthorizationDenialCode.GRANT_NOT_FOUND,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "revoke",
            "self_owned_grant_no_manager",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            404,
            "resource_not_found",
            "Resource not found",
        ),
        (
            "revoke",
            "self_owned_grant_manager",
            AuthorizationDenialCode.SELF_ROLE_REVOKE_FORBIDDEN,
            403,
            "self_role_revoke_forbidden",
            "Self role revocation is forbidden",
        ),
    ],
)
async def test_project_role_mutation_routes_conceal_denials_and_preserve_self_guards_atomically(
    monkeypatch: pytest.MonkeyPatch,
    invocation: str,
    operation: str,
    hidden_case: str,
    denial_code: AuthorizationDenialCode,
    expected_status: int,
    expected_code: str,
    message: str,
) -> None:
    project_id, grant_id, caller_id, target_id = uuid4(), uuid4(), uuid4(), uuid4()
    if hidden_case == "self_target_manager":
        target_id = caller_id
    persisted = {
        "idempotency": 0,
        "qualification_snapshot": 0,
        "project_role_grant": 0,
        "audit": 0,
        "invalidation": 0,
    }
    staged = persisted.copy()
    calls = {"reserve": 0, "complete_issue": 0, "complete_revoke": 0}

    class Session:
        rollback_count = 0
        commit_count = 0

        async def rollback(self) -> None:
            self.rollback_count += 1
            staged.update(dict.fromkeys(staged, 0))

        async def commit(self) -> None:
            self.commit_count += 1
            persisted.update(staged)

        def in_transaction(self) -> bool:
            return any(staged.values())

    class Repository:
        async def lock_project(self, selected_project_id):
            assert selected_project_id == project_id
            return SimpleNamespace(id=str(project_id), status="active")

        async def take_project_role_issue_lock(self, _key):
            return None

        async def lock_eligible_human(self, selected_target_id):
            assert selected_target_id == target_id
            if hidden_case in {
                "missing_target_no_manager",
                "inactive_target_no_manager",
                "nonhuman_target_no_manager",
                "missing_target_manager",
                "inactive_target_manager",
                "nonhuman_target_manager",
                "unauthorized_target_manager",
            }:
                return None
            return (SimpleNamespace(id=str(target_id)), SimpleNamespace(id=str(uuid4())))

        async def find_active_project_role(self, **_kwargs):
            return None

        async def lock_project_role_grant(self, **values):
            assert values["project_id"] == project_id
            assert values["grant_id"] == grant_id_value
            if hidden_case in {"nonexistent_grant", "cross_project_grant"}:
                return None
            grant = SimpleNamespace(
                id=values["grant_id"],
                project_id=str(project_id),
                actor_profile_id=str(caller_id),
                role="submitter",
                status="active",
                version=1,
                qualification_snapshot_id=uuid4(),
            )
            return grant, SimpleNamespace(id=grant.qualification_snapshot_id)

    class MutationService:
        def __init__(self, _session) -> None:
            self.repository = Repository()

        async def reserve(self, **_kwargs):
            calls["reserve"] += 1
            staged["idempotency"] += 1
            return SimpleNamespace(outcome="fresh", claim=object())

        async def complete_issue(self, **_kwargs):
            calls["complete_issue"] += 1
            for key in ("qualification_snapshot", "project_role_grant", "audit"):
                staged[key] += 1
            raise AssertionError("concealed issue must not reach completion")

        async def complete_revoke(self, **_kwargs):
            calls["complete_revoke"] += 1
            for key in ("project_role_grant", "audit", "invalidation"):
                staged[key] += 1
            raise AssertionError("concealed revoke must not reach completion")

    class Prepared:
        async def prepare(self, *_args):
            return object()

        async def consume(self, _handle, action_id, _prepared_input, resource):
            raise AuthorizationDenied(
                _project_role_denial_decision(action_id, resource.resource_id, denial_code)
            )

    session = Session()
    prepared = Prepared()
    resolved = SimpleNamespace(profile=SimpleNamespace(id=str(caller_id)))
    grant_id_value = grant_id
    monkeypatch.setattr(
        authorization_router,
        "ProjectRoleGrantMutationService",
        MutationService,
    )
    issue_payload = ProjectRoleGrantIssueBody(
        target_actor_profile_id=target_id,
        role=ProjectRole.SUBMITTER,
        qualification=_project_role_qualification(),
        reason="Bounded assignment",
    )
    revoke_payload = ProjectRoleGrantRevokeBody(reason="Bounded removal")

    if invocation == "http_route":
        app = create_app(Settings(environment="test"))

        async def session_dependency():
            try:
                yield session
            finally:
                await session.rollback()

        async def resolved_dependency():
            return resolved

        async def prepared_dependency():
            return prepared

        async def consume_rate() -> None:
            return None

        app.dependency_overrides[get_db_session] = session_dependency
        app.dependency_overrides[get_authorization_actor] = resolved_dependency
        app.dependency_overrides[get_prepared_authorization_service] = prepared_dependency
        app.dependency_overrides[enforce_admin_mutation_rate_limit] = consume_rate
        path = (
            f"/api/v1/projects/{project_id}/role-grants"
            if operation == "issue"
            else f"/api/v1/projects/{project_id}/role-grants/{grant_id}/revoke"
        )
        body = (
            issue_payload.model_dump(mode="json")
            if operation == "issue"
            else revoke_payload.model_dump(mode="json")
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                path,
                headers={"Idempotency-Key": str(uuid4())},
                json=body,
            )
        error = response.json()["error"]
        assert error["details"] == {}
        assert error["retryable"] is False
        assert UUID(error["correlation_id"])
        public_result = (
            response.status_code,
            {"code": error["code"], "message": error["message"]},
        )
    else:
        try:
            if operation == "issue":
                await authorization_router.issue_project_role_grant(
                    project_id=project_id,
                    payload=issue_payload,
                    idempotency_key=uuid4(),
                    resolved=resolved,  # type: ignore[arg-type]
                    prepared=prepared,  # type: ignore[arg-type]
                    session=session,  # type: ignore[arg-type]
                )
            else:
                await authorization_router.revoke_project_role_grant(
                    project_id=project_id,
                    grant_id=grant_id,
                    payload=revoke_payload,
                    idempotency_key=uuid4(),
                    resolved=resolved,  # type: ignore[arg-type]
                    prepared=prepared,  # type: ignore[arg-type]
                    session=session,  # type: ignore[arg-type]
                )
        except StructuredHTTPException as exc:
            public_result = (
                exc.status_code,
                {"code": exc.error_code, "message": exc.error_message},
            )
        else:
            raise AssertionError("concealed mutation unexpectedly succeeded")
        finally:
            await session.rollback()

    assert public_result == (
        expected_status,
        {"code": expected_code, "message": message},
    )
    assert calls == {"reserve": 1, "complete_issue": 0, "complete_revoke": 0}
    assert staged == dict.fromkeys(staged, 0)
    assert persisted == dict.fromkeys(persisted, 0)
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invocation", ["http_route", "direct_route"])
@pytest.mark.parametrize(
    ("operation", "project_state", "project_exists", "expected_status"),
    [
        ("issue", "draft", True, 201),
        ("issue", "active", True, 201),
        ("issue", "paused", True, 201),
        ("issue", "archived", True, 404),
        ("issue", "active", False, 404),
        ("revoke", "draft", True, 200),
        ("revoke", "active", True, 200),
        ("revoke", "paused", True, 200),
        ("revoke", "archived", True, 200),
    ],
)
async def test_project_role_mutation_routes_enforce_project_lifecycle_without_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    invocation: str,
    operation: str,
    project_state: str,
    project_exists: bool,
    expected_status: int,
) -> None:
    project_id, grant_id, caller_id, target_id, snapshot_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    staged = {
        "idempotency": 0,
        "qualification_snapshot": 0,
        "project_role_grant": 0,
        "audit": 0,
        "invalidation": 0,
    }
    persisted = staged.copy()
    calls = {"target_lookup": 0, "consume": 0, "complete": 0}

    class Session:
        commit_count = 0
        rollback_count = 0

        async def commit(self) -> None:
            self.commit_count += 1
            persisted.update(staged)
            staged.update(dict.fromkeys(staged, 0))

        async def rollback(self) -> None:
            self.rollback_count += 1
            staged.update(dict.fromkeys(staged, 0))

        def in_transaction(self) -> bool:
            return any(staged.values())

    class Repository:
        async def lock_project(self, selected_project_id):
            assert selected_project_id == project_id
            if not project_exists:
                return None
            return SimpleNamespace(id=str(project_id), status=project_state)

        async def take_project_role_issue_lock(self, _key):
            return None

        async def lock_eligible_human(self, selected_target_id):
            calls["target_lookup"] += 1
            assert selected_target_id == target_id
            return SimpleNamespace(id=str(target_id)), SimpleNamespace(id=str(uuid4()))

        async def find_active_project_role(self, **_kwargs):
            return None

        async def lock_project_role_grant(self, **values):
            assert values == {"project_id": project_id, "grant_id": grant_id}
            grant = SimpleNamespace(
                id=grant_id,
                qualification_snapshot_id=snapshot_id,
                project_id=str(project_id),
                actor_profile_id=str(target_id),
                role="submitter",
                status="active",
                version=1,
            )
            return grant, SimpleNamespace(id=snapshot_id)

    class MutationService:
        def __init__(self, _session) -> None:
            self.repository = Repository()

        async def reserve(self, **_kwargs):
            staged["idempotency"] += 1
            return SimpleNamespace(outcome="fresh", claim=object())

        async def complete_issue(self, **_kwargs):
            calls["complete"] += 1
            staged.update(
                {
                    "qualification_snapshot": 1,
                    "project_role_grant": 1,
                    "audit": 2,
                }
            )
            return ProjectRoleGrantMutationResponse(
                id=grant_id,
                qualification_snapshot_id=snapshot_id,
                project_id=project_id,
                actor_profile_id=target_id,
                role=ProjectRole.SUBMITTER,
                status="active",
                version=1,
            )

        async def complete_revoke(self, **_kwargs):
            calls["complete"] += 1
            staged.update({"project_role_grant": 1, "audit": 2, "invalidation": 1})
            return ProjectRoleGrantMutationResponse(
                id=grant_id,
                qualification_snapshot_id=snapshot_id,
                project_id=project_id,
                actor_profile_id=target_id,
                role=ProjectRole.SUBMITTER,
                status="revoked",
                version=2,
            )

    class Prepared:
        async def prepare(self, *_args):
            return object()

        async def consume(self, _handle, action_id, _prepared_input, resource):
            calls["consume"] += 1
            assert resource.project_status == project_state
            if operation == "issue" and project_state == "archived":
                raise AuthorizationDenied(
                    _project_role_denial_decision(
                        action_id,
                        resource.resource_id,
                        AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
                    )
                )
            return SimpleNamespace(allowed=True)

    session = Session()
    prepared = Prepared()
    resolved = SimpleNamespace(profile=SimpleNamespace(id=str(caller_id)))
    monkeypatch.setattr(
        authorization_router,
        "ProjectRoleGrantMutationService",
        MutationService,
    )
    issue_payload = ProjectRoleGrantIssueBody(
        target_actor_profile_id=target_id,
        role=ProjectRole.SUBMITTER,
        qualification=_project_role_qualification(),
        reason="Lifecycle assignment",
    )
    revoke_payload = ProjectRoleGrantRevokeBody(reason="Lifecycle removal")

    async def invoke_direct():
        if operation == "issue":
            return await authorization_router.issue_project_role_grant(
                project_id=project_id,
                payload=issue_payload,
                idempotency_key=uuid4(),
                resolved=resolved,  # type: ignore[arg-type]
                prepared=prepared,  # type: ignore[arg-type]
                session=session,  # type: ignore[arg-type]
            )
        return await authorization_router.revoke_project_role_grant(
            project_id=project_id,
            grant_id=grant_id,
            payload=revoke_payload,
            idempotency_key=uuid4(),
            resolved=resolved,  # type: ignore[arg-type]
            prepared=prepared,  # type: ignore[arg-type]
            session=session,  # type: ignore[arg-type]
        )

    if invocation == "http_route":
        app = create_app(Settings(environment="test"))

        async def session_dependency():
            try:
                yield session
            finally:
                if session.in_transaction():
                    await session.rollback()

        async def resolved_dependency():
            return resolved

        async def prepared_dependency():
            return prepared

        async def consume_rate() -> None:
            return None

        app.dependency_overrides[get_db_session] = session_dependency
        app.dependency_overrides[get_authorization_actor] = resolved_dependency
        app.dependency_overrides[get_prepared_authorization_service] = prepared_dependency
        app.dependency_overrides[enforce_admin_mutation_rate_limit] = consume_rate
        path = (
            f"/api/v1/projects/{project_id}/role-grants"
            if operation == "issue"
            else f"/api/v1/projects/{project_id}/role-grants/{grant_id}/revoke"
        )
        payload = issue_payload if operation == "issue" else revoke_payload
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                path,
                headers={"Idempotency-Key": str(uuid4())},
                json=payload.model_dump(mode="json"),
            )
        observed_status = response.status_code
        observed_body = response.json()
    else:
        try:
            result = await invoke_direct()
        except StructuredHTTPException as exc:
            observed_status = exc.status_code
            observed_body = {"error": {"code": exc.error_code, "message": exc.error_message}}
        else:
            observed_status = 201 if operation == "issue" else 200
            observed_body = result.model_dump(mode="json")
        finally:
            if session.in_transaction():
                await session.rollback()

    assert observed_status == expected_status
    if expected_status == 404:
        assert observed_body["error"]["code"] == "resource_not_found"
        assert observed_body["error"]["message"] == "Resource not found"
        assert persisted == dict.fromkeys(persisted, 0)
        assert calls["complete"] == 0
        assert session.commit_count == 0
        if not project_exists:
            assert calls == {"target_lookup": 0, "consume": 0, "complete": 0}
    else:
        expected_body = {
            "id": str(grant_id),
            "qualification_snapshot_id": str(snapshot_id),
            "project_id": str(project_id),
            "actor_profile_id": str(target_id),
            "role": "submitter",
            "status": "active" if operation == "issue" else "revoked",
            "version": 1 if operation == "issue" else 2,
        }
        assert observed_body == expected_body
        assert calls["consume"] == 1
        assert calls["complete"] == 1
        assert session.commit_count == 1
        assert persisted["idempotency"] == 1
        assert persisted["project_role_grant"] == 1
        assert persisted["audit"] == 2
        assert persisted["qualification_snapshot"] == (operation == "issue")
        assert persisted["invalidation"] == (operation == "revoke")


ART_CUSTODY_EXPECTATIONS = {
    "artifact.binding.read": (
        "artifact.binding.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.replica.read": (
        "artifact.replica.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.receipt.read": (
        "artifact.receipt.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification_job.read": (
        "artifact.verification_job.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification_job.retry": (
        "artifact.verification_job.retry",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.recovery_attempt.read": (
        "artifact.recovery_attempt.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.audit.read": (
        "artifact.audit.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "operations.artifact_storage_admission.read": (
        "operations.status.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification.execute": (
        "artifact.verification.execute",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.pending_work.scan": (
        "artifact.pending_work.scan",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.put_attempt.resolve": (
        "artifact.put_attempt.resolve",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.guide_source.ingest": (
        "artifact.guide_source.ingest",
        "WS-XINT-002-04A",
        "active",
    ),
    "artifact.guide_source.read": (
        "artifact.guide_source.read",
        "WS-AUTH-001-ART-03",
        "planned",
    ),
    "artifact.guide_source.binding.create": (
        "artifact.binding.create",
        "WS-AUTH-001-ART-03",
        "planned",
    ),
    "artifact.submission_bundle.prepare": (
        "submission.create",
        "WS-XINT-002-05A",
        "planned",
    ),
    "artifact.pre_submit.checker_input.materialize": (
        "artifact.checker_input.materialize",
        "WS-AUTH-001-ART-04B",
        "planned",
    ),
    "artifact.submission.binding.create": (
        "artifact.binding.create",
        "WS-AUTH-001-ART-05",
        "planned",
    ),
    "artifact.post_submit.checker_input.materialize": (
        "artifact.checker_input.materialize",
        "WS-AUTH-001-ART-06A",
        "planned",
    ),
    "artifact.checker_output.write": (
        "artifact.checker_output.write",
        "WS-AUTH-001-ART-06B",
        "planned",
    ),
    "artifact.review_packet.materialize": (
        "artifact.review_packet.materialize",
        "WS-XINT-002-07",
        "planned",
    ),
    "artifact.review_evidence.binding.create": (
        "artifact.binding.create",
        "WS-XINT-002-07",
        "planned",
    ),
    "artifact.checker_output.binding.create": (
        "artifact.binding.create",
        "WS-AUTH-001-ART-06B",
        "planned",
    ),
}

REV_CUSTODY_EXPECTATIONS = {
    "review.queue.read": ("review.queue.read", "WS-AUTH-001-REV-05", "planned"),
    "review.queue.inspect": ("review.queue.inspect", "WS-AUTH-001-REV-05", "planned"),
    "review.claim": ("review.claim", "WS-AUTH-001-REV-06", "planned"),
    "review.release": ("review.release", "WS-AUTH-001-REV-06", "planned"),
    "review.decline_preference": (
        "review.decline_preference",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.preference_expiry.run": (
        "operations.timer.run",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.lease_expiry.run": (
        "operations.timer.run",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.context.read": (
        "submission.read_for_review",
        "WS-AUTH-001-REV-07",
        "planned",
    ),
    "review.chain.read": ("review.chain.read", "WS-AUTH-001-REV-07", "planned"),
    "review.finding_evidence.ingest": (
        "review.decision",
        "WS-AUTH-001-REV-07",
        "planned",
    ),
    "review.decision": ("review.decision", "WS-AUTH-001-REV-08", "planned"),
    "review.finding_response_evidence.ingest": (
        "submission.create",
        "WS-AUTH-001-REV-09A",
        "planned",
    ),
    "review.lease.force_release": (
        "review.lease.force_release",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.routing.override": (
        "review.queue.override",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.routing.correct": (
        "review.queue.override",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.close": ("review.queue.override", "WS-AUTH-001-REV-11", "planned"),
    "review.reconcile.run": (
        "operations.reconcile.run",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.artifact_reference.reconcile": (
        "operations.reconcile.run",
        "WS-AUTH-001-REV-12",
        "planned",
    ),
    "review.projection.rebuild": (
        "operations.projection.rebuild",
        "WS-AUTH-001-REV-12",
        "planned",
    ),
}


def _admin_resource_context(
    request: AdminRoleGrantIssueRequest | AdminRoleGrantRevokeRequest,
    *,
    existing_idempotency_record: bool = False,
):
    if isinstance(request, AdminRoleGrantIssueRequest):
        return AdminRoleGrantIssueResourceContext(
            resource_type="admin_role_grant_issue",
            resource_id=request.target_actor_id,
            role=request.role,
            scope_type=request.scope_type,
            scope_project_id=request.scope_project_id,
        )
    return AdminRoleGrantResourceContext(
        resource_type="admin_role_grant",
        resource_id=request.grant_id,
        existing_idempotency_record=existing_idempotency_record,
    )


def test_closed_permission_and_action_catalogue_is_exact_and_non_executable() -> None:
    historical_permissions = frozenset(
        """actor.profile.read_self actor.profile.update_self actor.profile.read_any
        actor.profile.suspend actor.profile.reactivate actor.profile.deactivate
        actor.identity_link.read actor.identity_link.revoke actor.identity_link.reactivate
        actor.service.provision admin_role.read admin_role.grant admin_role.revoke
        project.create project.read project.update project.archive project.guide.manage
        project.effective_policy.manage project.task.manage project.review_policy.manage
        project.role_grant.read project.role_grant.manage task.queue.read task.claim
        submission.create submission.read_own submission.read_for_review review.queue.read
        review.queue.inspect review.claim review.release review.decline_preference
        review.decision review.lease.force_release review.chain.read contribution.read_self
        contribution.read_project compensation.policy.manage
        compensation.adapter_binding.manage compensation.award.read
        compensation.delivery.reconcile operations.status.read operations.timer.run
        operations.reconcile.run operations.outbox.retry operations.projection.rebuild
        audit.read audit.export""".split()
    )
    new_permissions = frozenset(
        """project.setup_diagnostic.read project.effective_policy.read
        operations.task.start_override operations.submission_gate.repair
        operations.checker.retry artifact.binding.read artifact.replica.read
        artifact.receipt.read artifact.verification_job.read
        artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read
        artifact.guide_source.ingest artifact.binding.create
        artifact.verification.execute artifact.pending_work.scan artifact.put_attempt.resolve
        artifact.guide_source.read artifact.checker_input.materialize
        artifact.checker_output.write artifact.review_packet.materialize
        review.queue.override""".split()
    )
    expected = {
        "actor.profile.read_self": ("actor.profile.read_self", "WS-AUTH-001-07B"),
        "actor.profile.update_self": ("actor.profile.update_self", "WS-AUTH-001-07B"),
        "operations.task.start_override": ("operations.task.start_override", "WS-AUTH-001-13"),
        "operations.submission_gate.repair": (
            "operations.submission_gate.repair",
            "WS-AUTH-001-14",
        ),
        "operations.checker.retry": ("operations.checker.retry", "WS-AUTH-001-14"),
        "submission.create": ("submission.create", "WS-AUTH-001-14"),
        **{
            action: (permission, owner)
            for action, (permission, owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
        },
        **{
            action: (permission, owner)
            for action, (permission, owner, _availability) in ART_CUSTODY_EXPECTATIONS.items()
        },
        "authorization.permission_catalogue.read": ("admin_role.read", "WS-AUTH-001-08"),
        "authorization.admin_role_definitions.read": ("admin_role.read", "WS-AUTH-001-08"),
        "admin_role_grant.list": ("admin_role.read", "WS-AUTH-001-08"),
        "actor.admin_role_grant_history.read": ("admin_role.read", "WS-AUTH-001-08"),
        "admin_role_grant.issue": ("admin_role.grant", "WS-AUTH-001-08"),
        "admin_role_grant.revoke": ("admin_role.revoke", "WS-AUTH-001-08"),
        "admin_role_grant.bootstrap": ("admin_role.grant", "WS-AUTH-001-08"),
        "actor.profile.read": ("actor.profile.read_any", "WS-AUTH-001-09C"),
        "actor.profile.suspend": ("actor.profile.suspend", "WS-AUTH-001-09D-A"),
        "actor.profile.reactivate": ("actor.profile.reactivate", "WS-AUTH-001-09D-A"),
        "actor.profile.deactivate": ("actor.profile.deactivate", "WS-AUTH-001-09D-A"),
        "actor.identity_link.read": ("actor.identity_link.read", "WS-AUTH-001-09C"),
        "actor.identity_link.revoke": ("actor.identity_link.revoke", "WS-AUTH-001-09D-B"),
        "actor.identity_link.reactivate": (
            "actor.identity_link.reactivate",
            "WS-AUTH-001-09D-B",
        ),
        "actor.service.provision": ("actor.service.provision", "WS-AUTH-001-09B"),
        "project.contributor_candidate.list": (
            "project.role_grant.manage",
            "WS-AUTH-001-10B",
        ),
        "project_role_grant.list": ("project.role_grant.read", "WS-AUTH-001-10B"),
        "project_role_grant.read": ("project.role_grant.read", "WS-AUTH-001-10B"),
        "project_role_grant.issue": ("project.role_grant.manage", "WS-AUTH-001-10C"),
        "project_role_grant.revoke": ("project.role_grant.manage", "WS-AUTH-001-10C"),
        "project.read": ("project.read", "WS-AUTH-001-11B"),
        "actor.authorization_context.read": (
            "actor.profile.read_self",
            "WS-AUTH-001-11B",
        ),
        "project.setup_run.read": (
            "project.setup_diagnostic.read",
            "WS-AUTH-001-11C1",
        ),
        "project.guide_sufficiency_report.list": (
            "project.setup_diagnostic.read",
            "WS-AUTH-001-11C1",
        ),
        "project.guide_sufficiency_report.read": (
            "project.setup_diagnostic.read",
            "WS-AUTH-001-11C1",
        ),
        "project.submission_artifact_policy.list": (
            "project.effective_policy.read",
            "WS-AUTH-001-11C1",
        ),
        "project.submission_artifact_policy.read": (
            "project.effective_policy.read",
            "WS-AUTH-001-11C1",
        ),
        "project.post_submit_checker_policy_setup.read": (
            "project.effective_policy.read",
            "WS-AUTH-001-11C1",
        ),
        "project.effective_submission_artifact_policy.read": (
            "project.effective_policy.read",
            "WS-AUTH-001-11C2",
        ),
        "project.pre_submit_checker_policy.read": (
            "project.effective_policy.read",
            "WS-AUTH-001-11C2",
        ),
        "project.active_guide.read": ("project.read", "WS-AUTH-001-11C2"),
        "project.create": ("project.create", "WS-AUTH-001-12C"),
        "project.guide.create": ("project.guide.manage", "WS-AUTH-001-12D"),
        "project.guide.update": ("project.guide.manage", "WS-AUTH-001-12D"),
        "project.guide_source_snapshot.create": (
            "project.guide.manage",
            "WS-AUTH-001-12D",
        ),
        "project.review_policy.update": (
            "project.review_policy.manage",
            "WS-AUTH-001-12D2",
        ),
        "project.revision_policy.update": (
            "project.review_policy.manage",
            "WS-AUTH-001-12D2",
        ),
        "project.guide_sufficiency_report.create": (
            "project.guide.manage",
            "WS-AUTH-001-12E",
        ),
        "project.guide_sufficiency.run": (
            "project.guide.manage",
            "WS-AUTH-001-12E",
        ),
        "project.guide_sufficiency.warnings.acknowledge": (
            "project.guide.manage",
            "WS-AUTH-001-12E",
        ),
        "project.submission_artifact_policy.create": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12F",
        ),
        "project.submission_artifact_policy.derive": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12F",
        ),
        "project.submission_artifact_policy.update": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12F",
        ),
        "project.submission_artifact_policy.approve": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12F",
        ),
        "project.post_submit_checker_policy.approve": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12G",
        ),
        "project.post_submit_checker_policy.correction.request": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12G",
        ),
        "project.post_submit_checker_policy.derive": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12G",
        ),
        "project.setup_run.update": ("project.guide.manage", "WS-AUTH-001-12B2"),
        "project.guide.activate": ("project.guide.manage", "WS-AUTH-001-12H"),
    }
    assert {item.value for item in HISTORICAL_PERMISSION_IDS} == historical_permissions
    assert {item.value for item in NEW_PERMISSION_IDS} == new_permissions
    assert {item.value for item in PERMISSION_IDS} == historical_permissions | new_permissions
    assert len(ACTION_IDS) == len(ACTION_DEFINITIONS) == len(ACTION_BY_ID) == 96
    assert set(ACTION_BY_ID) == ACTION_IDS
    assert {definition.owner for definition in ACTION_DEFINITIONS} == set(ActionOwner)
    assert {
        definition.action_id
        for definition in ACTION_DEFINITIONS
        if definition.availability is ActionAvailability.ACTIVE
    } == {
        ActionId.ACTOR_PROFILE_READ_SELF,
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        ActionId.ADMIN_ROLE_GRANT_LIST,
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
        ActionId.ACTOR_SERVICE_PROVISION,
        ActionId.ACTOR_PROFILE_SUSPEND,
        ActionId.ACTOR_PROFILE_REACTIVATE,
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        ActionId.PROJECT_CREATE,
        ActionId.PROJECT_READ,
        ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        ActionId.ARTIFACT_PENDING_WORK_SCAN,
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
    }
    assert {
        definition.action_id.value: (
            definition.permission_id.value,
            definition.owner.value,
        )
        for definition in ACTION_DEFINITIONS
    } == expected
    assert {
        action: (
            ACTION_BY_ID[ActionId(action)].permission_id.value,
            ACTION_BY_ID[ActionId(action)].owner.value,
            ACTION_BY_ID[ActionId(action)].availability.value,
        )
        for action in ART_CUSTODY_EXPECTATIONS
    } == ART_CUSTODY_EXPECTATIONS
    assert {
        action: (
            ACTION_BY_ID[ActionId(action)].permission_id.value,
            ACTION_BY_ID[ActionId(action)].owner.value,
            ACTION_BY_ID[ActionId(action)].availability.value,
        )
        for action in REV_CUSTODY_EXPECTATIONS
    } == REV_CUSTODY_EXPECTATIONS
    assert {
        owner: sum(definition.owner is owner for definition in ACTION_DEFINITIONS)
        for owner in {
            ActionOwner.AUTH_ART_02D_OPERATOR,
            ActionOwner.AUTH_ART_02D_INTERNAL,
            ActionOwner.AUTH_ART_03,
            ActionOwner.AUTH_ART_04B,
            ActionOwner.AUTH_ART_05,
            ActionOwner.AUTH_ART_06A,
            ActionOwner.AUTH_ART_06B,
            ActionOwner.XINT_002_04A,
            ActionOwner.XINT_002_05A,
            ActionOwner.XINT_002_07,
        }
    } == {
        ActionOwner.AUTH_ART_02D_OPERATOR: 8,
        ActionOwner.AUTH_ART_02D_INTERNAL: 3,
        ActionOwner.AUTH_ART_03: 2,
        ActionOwner.AUTH_ART_04B: 1,
        ActionOwner.AUTH_ART_05: 1,
        ActionOwner.AUTH_ART_06A: 1,
        ActionOwner.AUTH_ART_06B: 2,
        ActionOwner.XINT_002_04A: 1,
        ActionOwner.XINT_002_05A: 1,
        ActionOwner.XINT_002_07: 2,
    }
    assert all(not owner.value.startswith("WS-ART-") for owner in ActionOwner)
    assert {
        owner: sum(definition.owner is owner for definition in ACTION_DEFINITIONS)
        for owner in {
            ActionOwner.AUTH_REV_05,
            ActionOwner.AUTH_REV_06,
            ActionOwner.AUTH_REV_07,
            ActionOwner.AUTH_REV_08,
            ActionOwner.AUTH_REV_09A,
            ActionOwner.AUTH_REV_11,
            ActionOwner.AUTH_REV_12,
        }
    } == {
        ActionOwner.AUTH_REV_05: 2,
        ActionOwner.AUTH_REV_06: 5,
        ActionOwner.AUTH_REV_07: 3,
        ActionOwner.AUTH_REV_08: 1,
        ActionOwner.AUTH_REV_09A: 1,
        ActionOwner.AUTH_REV_11: 5,
        ActionOwner.AUTH_REV_12: 2,
    }
    assert all(not owner.value.startswith("WS-REV-") for owner in ActionOwner)
    assert {
        "review.revision_context.repair",
        "review.revision_context.legacy_close",
        "review.revision_obligation.close",
        "review.lifecycle.activation.manage",
    }.isdisjoint(action.value for action in ACTION_IDS)
    assert (
        sum(
            definition.availability is ActionAvailability.ACTIVE
            for definition in ACTION_DEFINITIONS
        )
        == 38
    )
    assert (
        sum(
            definition.availability is ActionAvailability.PLANNED
            for definition in ACTION_DEFINITIONS
        )
        == 58
    )
    assert resolve_executable_action(ActionId.ACTOR_PROFILE_READ_SELF).permission_id is (
        PermissionId.ACTOR_PROFILE_READ_SELF
    )
    with pytest.raises(ValueError, match="not active"):
        resolve_executable_action(ActionId.REVIEW_QUEUE_READ)
    with pytest.raises(TypeError):
        ACTION_BY_ID[ActionId.ACTOR_PROFILE_READ_SELF] = ACTION_DEFINITIONS[0]


def test_project_mutation_resources_and_prepared_scopes_are_closed() -> None:
    """Bind every planned project mutation to one typed system/project scope."""
    project_id, guide_id, snapshot_id, report_id = (uuid4() for _ in range(4))
    review_id, revision_id, submission_policy_id, checker_policy_id = (uuid4() for _ in range(4))
    setup_run_id, operation_id, requested_project_id = (uuid4() for _ in range(3))
    setup_task_id, setup_correlation_id = uuid4(), uuid4()
    setup_custody_by_step = {
        step: ProjectSetupServiceCustodyContext(
            setup_run_id=setup_run_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=snapshot_id,
            setup_generation=1,
            expected_step=step,
            task_id=setup_task_id,
            correlation_id=setup_correlation_id,
            stale_output_digest=DIGEST,
        )
        for step in (
            "guide_sufficiency",
            "submission_artifact_policy",
            "post_submit_policy",
        )
    }
    create_resource = ProjectCreateResourceContext(
        resource_type="project_create",
        resource_id=operation_id,
        requested_project_id=requested_project_id,
        operation_generation=1,
    )
    guide_resources = {
        ActionId.PROJECT_GUIDE_CREATE: ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="create",
            guide_exists=False,
            operation_generation=1,
        ),
        ActionId.PROJECT_GUIDE_UPDATE: ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="update",
            guide_exists=True,
            guide_status="draft",
            guide_version="1",
            operation_generation=1,
        ),
    }
    source_resource = ProjectGuideSourceSnapshotMutationResourceContext(
        resource_type="project_guide_source_snapshot_mutation",
        resource_id=snapshot_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="1",
        guide_status="draft",
        source_snapshot_id=snapshot_id,
        operation_generation=1,
    )
    review_resource = ProjectReviewPolicyMutationResourceContext(
        resource_type="project_review_policy_mutation",
        resource_id=review_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="1",
        review_policy_id=review_id,
        policy_generation=1,
    )
    revision_resource = ProjectRevisionPolicyMutationResourceContext(
        resource_type="project_revision_policy_mutation",
        resource_id=revision_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="1",
        revision_policy_id=revision_id,
        policy_generation=1,
    )
    sufficiency_resources = {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE: (
            ProjectGuideSufficiencyMutationResourceContext(
                resource_type="project_guide_sufficiency_mutation",
                resource_id=report_id,
                scope_project_id=project_id,
                guide_id=guide_id,
                guide_version="1",
                source_snapshot_id=snapshot_id,
                source_snapshot_hash=DIGEST,
                target_kind="report",
                execution_kind="human",
                sufficiency_report_id=report_id,
                setup_generation=1,
            )
        ),
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN: (
            ProjectGuideSufficiencyMutationResourceContext(
                resource_type="project_guide_sufficiency_mutation",
                resource_id=snapshot_id,
                scope_project_id=project_id,
                guide_id=guide_id,
                guide_version="1",
                source_snapshot_id=snapshot_id,
                source_snapshot_hash=DIGEST,
                target_kind="run",
                execution_kind="setup_service",
                setup_generation=1,
                stale_output_digest=DIGEST,
                setup_service_custody=setup_custody_by_step["guide_sufficiency"],
            )
        ),
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE: (
            ProjectGuideSufficiencyMutationResourceContext(
                resource_type="project_guide_sufficiency_mutation",
                resource_id=report_id,
                scope_project_id=project_id,
                guide_id=guide_id,
                guide_version="1",
                source_snapshot_id=snapshot_id,
                source_snapshot_hash=DIGEST,
                target_kind="warning_acknowledgement",
                execution_kind="human",
                sufficiency_report_id=report_id,
                setup_generation=1,
            )
        ),
    }
    submission_resources = {
        action_id: ProjectSubmissionArtifactPolicyMutationResourceContext(
            resource_type="project_submission_artifact_policy_mutation",
            resource_id=submission_policy_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version="1",
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=DIGEST,
            target_kind=target_kind,
            execution_kind="setup_service" if target_kind == "derive" else "human",
            policy_id=submission_policy_id,
            policy_generation=1,
            setup_generation=1,
            stale_output_digest=DIGEST if target_kind == "derive" else None,
            setup_service_custody=(
                setup_custody_by_step["submission_artifact_policy"]
                if target_kind == "derive"
                else None
            ),
        )
        for action_id, target_kind in (
            (ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE, "create"),
            (ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE, "derive"),
            (ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE, "update"),
            (ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE, "approve"),
        )
    }
    checker_resources = {
        action_id: ProjectPostSubmitCheckerPolicyMutationResourceContext(
            resource_type="project_post_submit_checker_policy_mutation",
            resource_id=checker_policy_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            guide_version="1",
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=DIGEST,
            target_kind=target_kind,
            execution_kind="setup_service" if target_kind == "derive" else "human",
            checker_policy_id=checker_policy_id,
            setup_generation=1,
            lifecycle_status="draft",
            compiled_policy_digest=DIGEST,
            setup_service_custody=(
                setup_custody_by_step["post_submit_policy"] if target_kind == "derive" else None
            ),
        )
        for action_id, target_kind in (
            (ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_APPROVE, "approve"),
            (
                ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_CORRECTION_REQUEST,
                "correction_request",
            ),
            (ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE, "derive"),
        )
    }
    setup_resource = ProjectSetupRunMutationResourceContext(
        resource_type="project_setup_run_mutation",
        resource_id=setup_run_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        setup_run_id=setup_run_id,
        setup_generation=1,
        expected_step="guide_sufficiency",
        task_id=uuid4(),
        correlation_id=uuid4(),
        stale_output_digest=DIGEST,
    )
    activation_resource = ProjectGuideActivationResourceContext(
        resource_type="project_guide_activation",
        resource_id=guide_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="1",
        source_snapshot_id=snapshot_id,
        sufficiency_report_id=report_id,
        submission_artifact_policy_id=submission_policy_id,
        pre_submit_checker_policy_id=uuid4(),
        post_submit_checker_policy_id=checker_policy_id,
        review_policy_id=review_id,
        revision_policy_id=revision_id,
        active_bundle_digest=DIGEST,
        activation_generation=1,
    )
    resources = {
        ActionId.PROJECT_CREATE: create_resource,
        **guide_resources,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE: source_resource,
        ActionId.PROJECT_REVIEW_POLICY_UPDATE: review_resource,
        ActionId.PROJECT_REVISION_POLICY_UPDATE: revision_resource,
        **sufficiency_resources,
        **submission_resources,
        **checker_resources,
        ActionId.PROJECT_SETUP_RUN_UPDATE: setup_resource,
        ActionId.PROJECT_GUIDE_ACTIVATE: activation_resource,
    }
    assert set(resources) == set(PROJECT_MUTATION_RESOURCE_BY_ACTION)
    for action_id, resource in resources.items():
        assert AuthorizationService._admin_resource_matches(action_id, resource)
        scope = PreparedAuthorizationService._scope_from_resource(action_id, resource)
        if action_id is ActionId.PROJECT_CREATE:
            assert scope == PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
        else:
            assert scope == PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=project_id,
            )
    assert not AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        review_resource,
    )
    assert not AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_GUIDE_UPDATE,
        guide_resources[ActionId.PROJECT_GUIDE_CREATE],
    )
    assert not AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
        sufficiency_resources[ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN],
    )
    assert not AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE,
        submission_resources[ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE],
    )
    assert not AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_APPROVE,
        checker_resources[ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE],
    )
    human_sufficiency_run = sufficiency_resources[
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
    ].model_copy(
        update={
            "execution_kind": "human",
            "setup_service_custody": None,
        }
    )
    assert AuthorizationService._admin_resource_matches(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        ProjectGuideSufficiencyMutationResourceContext.model_validate(
            human_sufficiency_run.model_dump()
        ),
    )
    with pytest.raises(ValidationError):
        ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=uuid4(),
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="update",
            guide_exists=True,
            guide_status="draft",
            guide_version="1",
            operation_generation=1,
        )
    for context_type, service_resource in (
        (
            ProjectGuideSufficiencyMutationResourceContext,
            sufficiency_resources[ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN],
        ),
        (
            ProjectSubmissionArtifactPolicyMutationResourceContext,
            submission_resources[ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE],
        ),
        (
            ProjectPostSubmitCheckerPolicyMutationResourceContext,
            checker_resources[ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE],
        ),
    ):
        missing_custody = service_resource.model_dump()
        missing_custody["setup_service_custody"] = None
        with pytest.raises(ValidationError, match="service execution requires exact setup custody"):
            context_type.model_validate(missing_custody)
        if context_type is not ProjectGuideSufficiencyMutationResourceContext:
            human_derive = service_resource.model_dump()
            human_derive["execution_kind"] = "human"
            human_derive["setup_service_custody"] = None
            with pytest.raises(
                ValidationError, match="derivation requires setup-service authority"
            ):
                context_type.model_validate(human_derive)
        wrong_lineage = service_resource.model_dump()
        wrong_lineage["setup_service_custody"]["scope_project_id"] = uuid4()
        with pytest.raises(ValidationError, match="setup lineage is inconsistent"):
            context_type.model_validate(wrong_lineage)
        wrong_generation = service_resource.model_dump()
        wrong_generation["setup_service_custody"]["setup_generation"] = 2
        with pytest.raises(ValidationError, match="setup generation is inconsistent"):
            context_type.model_validate(wrong_generation)
        wrong_step = service_resource.model_dump()
        wrong_step["setup_service_custody"]["expected_step"] = "post_submit_policy"
        if context_type is ProjectPostSubmitCheckerPolicyMutationResourceContext:
            wrong_step["setup_service_custody"]["expected_step"] = "guide_sufficiency"
        with pytest.raises(ValidationError, match="setup-service step is inconsistent"):
            context_type.model_validate(wrong_step)
        wrong_stale_output = service_resource.model_dump()
        wrong_stale_output["setup_service_custody"]["stale_output_digest"] = "sha256:" + "b" * 64
        with pytest.raises(ValidationError, match="stale output is inconsistent"):
            context_type.model_validate(wrong_stale_output)
        changed_task = service_resource.model_copy(
            update={
                "setup_service_custody": service_resource.setup_service_custody.model_copy(
                    update={"task_id": uuid4(), "correlation_id": uuid4()}
                )
            }
        )
        assert changed_task != service_resource


def test_obsolete_artifact_upload_authority_is_historical_only() -> None:
    """Reject obsolete upload authority outside exact immutable/deletion evidence."""
    repository_root = Path(__file__).resolve().parents[2]
    obsolete = {
        *(
            f"artifact.upload_session.{suffix}"
            for suffix in ("create", "read", "seal", "cancel", "expire")
        ),
        "artifact.upload_" + "item.write",
    }
    historical_handoff = (
        ".agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_ART_HANDOFF.md"
    )
    allowed = {
        "backend/alembic/versions/0021_authorization_action_evidence.py",
        "backend/alembic/versions/0022_bootstrap_admin_grants.py",
        "backend/alembic/versions/0023_service_actor_identity.py",
        "backend/alembic/versions/0036_art_auth_catalogue_reconciliation.py",
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-07A-closed-permission-action-catalogue.md",
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-09-actor-state-service-actors.md",
        ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-09A-service-identity-foundation.md",
        historical_handoff,
    }
    assert "Historical immutable handoff provenance" in (
        repository_root / historical_handoff
    ).read_text(encoding="utf-8")
    found: set[str] = set()
    ignored_parts = {
        ".git",
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "sheets",
    }
    for path in repository_root.rglob("*"):
        if not path.is_file() or ignored_parts.intersection(path.parts):
            continue
        try:
            text_value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(identifier in text_value for identifier in obsolete):
            found.add(path.relative_to(repository_root).as_posix())
    assert found == allowed


def test_fixed_service_action_matrix_and_activation_are_exact_and_immutable() -> None:
    expected = {
        ServiceIdentity.ARTIFACT_VERIFIER: {"artifact.verification.execute"},
        ServiceIdentity.ARTIFACT_PUT_RESOLVER: {"artifact.put_attempt.resolve"},
        ServiceIdentity.ARTIFACT_SCHEDULER: {
            "artifact.pending_work.scan",
        },
        ServiceIdentity.ARTIFACT_BINDING: {
            "artifact.guide_source.binding.create",
            "artifact.submission.binding.create",
            "artifact.checker_output.binding.create",
            "artifact.review_evidence.binding.create",
        },
        ServiceIdentity.ARTIFACT_GUIDE_READER: {"artifact.guide_source.read"},
        ServiceIdentity.ARTIFACT_MATERIALIZER: {
            "artifact.pre_submit.checker_input.materialize",
            "artifact.post_submit.checker_input.materialize",
            "artifact.review_packet.materialize",
        },
        ServiceIdentity.ARTIFACT_CHECKER_OUTPUT: {"artifact.checker_output.write"},
        ServiceIdentity.PROJECT_SETUP: {
            "project.guide_sufficiency.run",
            "project.submission_artifact_policy.derive",
            "project.post_submit_checker_policy.derive",
            "project.setup_run.update",
        },
    }
    assert set(SERVICE_ACTIONS_BY_IDENTITY) == SERVICE_IDENTITIES
    assert {
        identity: {action.value for action in actions}
        for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items()
    } == expected
    assert sum(map(len, SERVICE_ACTIONS_BY_IDENTITY.values())) == 16
    project_setup_actions = SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.PROJECT_SETUP]
    assert {
        action: (
            ACTION_BY_ID[action].permission_id,
            ACTION_BY_ID[action].owner,
            ACTION_BY_ID[action].availability,
        )
        for action in project_setup_actions
    } == {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN: (
            PermissionId.PROJECT_GUIDE_MANAGE,
            ActionOwner.AUTH_12E,
            ActionAvailability.PLANNED,
        ),
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE: (
            PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
            ActionOwner.AUTH_12F,
            ActionAvailability.PLANNED,
        ),
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE: (
            PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
            ActionOwner.AUTH_12G,
            ActionAvailability.PLANNED,
        ),
        ActionId.PROJECT_SETUP_RUN_UPDATE: (
            PermissionId.PROJECT_GUIDE_MANAGE,
            ActionOwner.AUTH_12B2,
            ActionAvailability.PLANNED,
        ),
    }
    active_internal = {
        ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        ActionId.ARTIFACT_PENDING_WORK_SCAN,
    }
    assert {
        action
        for actions in SERVICE_ACTIONS_BY_IDENTITY.values()
        for action in actions
        if ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
    } == active_internal
    assert all(
        ACTION_BY_ID[action].availability is ActionAvailability.PLANNED
        for actions in SERVICE_ACTIONS_BY_IDENTITY.values()
        for action in actions
        if action not in active_internal
    )
    with pytest.raises(TypeError):
        SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.ARTIFACT_VERIFIER] = frozenset()  # type: ignore[index]


def _parse_custody_table(document: Path, expected_actions: set[str]) -> dict[str, str]:
    rows = document.read_text(encoding="utf-8").splitlines()
    for header_index, row in enumerate(rows):
        if row not in {
            "| AUTH activation custodian | Exact planned ActionIds |",
            "| AUTH activation custodian | Exact ActionIds and current availability |",
            "| AUTH activation chunk | Exact planned ActionIds |",
        }:
            continue
        parsed: dict[str, str] = {}
        duplicates: set[str] = set()
        for table_row in rows[header_index + 2 :]:
            if not table_row.startswith("|"):
                break
            cells = [cell.strip() for cell in table_row.split("|")]
            assert len(cells) == 4
            owner = cells[1].strip("`")
            for action in cells[2].split("`")[1::2]:
                if action in parsed:
                    duplicates.add(action)
                parsed[action] = owner
        assert duplicates == set()
        if set(parsed) == expected_actions:
            return parsed
    raise AssertionError(f"exact custody table missing from {document}")


def test_art_custody_documentation_matches_the_independent_catalogue_fixture() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    custody_documents = (
        repository_root / "docs/spec_authorization_service.md",
        repository_root
        / ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service"
        / "ACTIVATION_CUSTODY.md",
    )
    expected_custody = {
        action: owner
        for action, (_permission, owner, _availability) in ART_CUSTODY_EXPECTATIONS.items()
    }
    expected_owner_counts = {
        "WS-AUTH-001-ART-02D-OPERATOR": 8,
        "WS-AUTH-001-ART-02D-INTERNAL": 3,
        "WS-AUTH-001-ART-03": 2,
        "WS-XINT-002-04A": 1,
        "WS-XINT-002-05A": 1,
        "WS-AUTH-001-ART-04B": 1,
        "WS-AUTH-001-ART-05": 1,
        "WS-AUTH-001-ART-06A": 1,
        "WS-AUTH-001-ART-06B": 2,
        "WS-XINT-002-07": 2,
    }

    for document in custody_documents:
        parsed = _parse_custody_table(document, set(expected_custody))
        assert parsed == expected_custody
        assert {
            owner: sum(parsed_owner == owner for parsed_owner in parsed.values())
            for owner in set(parsed.values())
        } == expected_owner_counts

    spec_rows = (
        (repository_root / "docs/spec_authorization_service.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    parsed_permissions: dict[str, str] = {}
    for row in spec_rows:
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 6:
            continue
        action = cells[1].strip("`")
        if action in ART_CUSTODY_EXPECTATIONS:
            assert action not in parsed_permissions
            parsed_permissions[action] = cells[2].strip("`")
    assert parsed_permissions == {
        action: permission
        for action, (permission, _owner, _availability) in ART_CUSTODY_EXPECTATIONS.items()
    }

    operations = (repository_root / "docs/operations_authorization_service.md").read_text(
        encoding="utf-8"
    )
    assert "all 22 ART rows to ten exact activation custodians" in operations
    assert "all 19 REV\nrows to seven exact AUTH custodians" in operations
    assert "transfer adds no migration; the later WS-XINT-002-01" in operations
    assert "does not grant Operator" in operations
    assert "verification retry remains independently gated" in operations
    assert (
        "71 PermissionIds, 96 ActionIds, 37 active actions, and\n59 planned actions" in operations
    )


def test_rev_custody_documentation_matches_the_independent_catalogue_fixture() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    custody_documents = (
        repository_root / "docs/spec_authorization_service.md",
        repository_root
        / ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service"
        / "ACTIVATION_CUSTODY.md",
    )
    expected_custody = {
        action: owner
        for action, (_permission, owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
    }
    expected_owner_counts = {
        "WS-AUTH-001-REV-05": 2,
        "WS-AUTH-001-REV-06": 5,
        "WS-AUTH-001-REV-07": 3,
        "WS-AUTH-001-REV-08": 1,
        "WS-AUTH-001-REV-09A": 1,
        "WS-AUTH-001-REV-11": 5,
        "WS-AUTH-001-REV-12": 2,
    }
    for document in custody_documents:
        parsed = _parse_custody_table(document, set(expected_custody))
        assert parsed == expected_custody
        assert {
            owner: sum(parsed_owner == owner for parsed_owner in parsed.values())
            for owner in set(parsed.values())
        } == expected_owner_counts

    spec_rows = (
        (repository_root / "docs/spec_authorization_service.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    parsed_permissions: dict[str, str] = {}
    for row in spec_rows:
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 5:
            continue
        action = cells[1].strip("`")
        if action in REV_CUSTODY_EXPECTATIONS:
            assert action not in parsed_permissions
            parsed_permissions[action] = cells[2].strip("`")
    assert parsed_permissions == {
        action: permission
        for action, (permission, _owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
    }

    operations = (repository_root / "docs/operations_authorization_service.md").read_text(
        encoding="utf-8"
    )
    assert "all 19 REV\nrows to seven exact AUTH custodians" in operations
    assert "all 19 REV actions remain planned and unavailable" in operations
    assert "The REV transfer\nadds no migration" in operations
    assert "four proposed REV lifecycle actions remain\nunregistered" in operations


@pytest.mark.parametrize(
    "mutation",
    ["missing_identity", "extra_action", "duplicate_action", "swapped_rows"],
)
def test_fixed_service_action_matrix_construction_fails_closed(mutation: str) -> None:
    rows = dict(SERVICE_ACTIONS_BY_IDENTITY)
    if mutation == "missing_identity":
        rows.pop(ServiceIdentity.ARTIFACT_VERIFIER)
    elif mutation == "extra_action":
        rows[ServiceIdentity.ARTIFACT_VERIFIER] = frozenset(
            {ActionId.ARTIFACT_VERIFICATION_EXECUTE, ActionId.ARTIFACT_AUDIT_READ}
        )
    elif mutation == "duplicate_action":
        rows[ServiceIdentity.ARTIFACT_PUT_RESOLVER] = frozenset(
            {ActionId.ARTIFACT_VERIFICATION_EXECUTE}
        )
    else:
        rows[ServiceIdentity.ARTIFACT_VERIFIER], rows[ServiceIdentity.ARTIFACT_PUT_RESOLVER] = (
            rows[ServiceIdentity.ARTIFACT_PUT_RESOLVER],
            rows[ServiceIdentity.ARTIFACT_VERIFIER],
        )
    with pytest.raises(RuntimeError, match="service action matrix"):
        _index_service_actions(rows)


@pytest.mark.parametrize("metadata", ["permission", "owner", "availability"])
def test_fixed_service_action_matrix_rejects_metadata_drift(
    metadata: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = ActionId.ARTIFACT_VERIFICATION_EXECUTE
    definition = ACTION_BY_ID[action]
    if metadata == "permission":
        changed = replace(definition, permission_id=PermissionId.ARTIFACT_PENDING_WORK_SCAN)
    elif metadata == "owner":
        changed = replace(definition, owner=ActionOwner.AUTH_ART_03)
    else:
        changed = replace(definition, availability=ActionAvailability.PLANNED)
    action_index = dict(ACTION_BY_ID)
    action_index[action] = changed
    monkeypatch.setattr(authorization_catalogue, "ACTION_BY_ID", action_index)
    with pytest.raises(RuntimeError, match="service action matrix metadata mismatch"):
        _index_service_actions(dict(SERVICE_ACTIONS_BY_IDENTITY))


def test_administrative_role_policy_and_definition_responses_are_exact() -> None:
    expected_permissions = {
        AdminRole.ACCESS_ADMINISTRATOR: """actor.profile.read_any actor.profile.suspend
            actor.profile.reactivate actor.profile.deactivate actor.identity_link.read
            actor.identity_link.revoke actor.identity_link.reactivate actor.service.provision
            admin_role.read admin_role.grant admin_role.revoke audit.read audit.export""".split(),
        AdminRole.OPERATOR: """project.read project.setup_diagnostic.read
            project.effective_policy.read review.queue.inspect review.lease.force_release
            contribution.read_project compensation.award.read operations.status.read
            operations.timer.run operations.reconcile.run operations.outbox.retry
            operations.projection.rebuild operations.task.start_override
            operations.submission_gate.repair operations.checker.retry artifact.binding.read
            artifact.replica.read artifact.receipt.read artifact.verification_job.read
            artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read
            audit.read""".split(),
        AdminRole.PROJECT_MANAGER: """project.create project.read project.setup_diagnostic.read
            project.effective_policy.read project.update project.archive
            project.guide.manage project.effective_policy.manage project.task.manage
            project.review_policy.manage project.role_grant.read project.role_grant.manage
            artifact.guide_source.ingest
            review.queue.inspect contribution.read_project compensation.award.read
            audit.read""".split(),
        AdminRole.FINANCE_AUTHORITY: """project.read contribution.read_project
            compensation.policy.manage compensation.adapter_binding.manage
            compensation.award.read compensation.delivery.reconcile audit.read""".split(),
        AdminRole.AUDIT_AUTHORITY: """actor.profile.read_any actor.identity_link.read
            admin_role.read project.read project.setup_diagnostic.read
            project.effective_policy.read project.role_grant.read review.queue.inspect
            review.chain.read contribution.read_project compensation.award.read audit.read
            audit.export""".split(),
    }
    expected_scopes = {
        AdminRole.ACCESS_ADMINISTRATOR: [AdminScope.SYSTEM],
        AdminRole.OPERATOR: [AdminScope.SYSTEM],
        AdminRole.PROJECT_MANAGER: [AdminScope.SYSTEM, AdminScope.PROJECT],
        AdminRole.FINANCE_AUTHORITY: [AdminScope.SYSTEM, AdminScope.PROJECT],
        AdminRole.AUDIT_AUTHORITY: [AdminScope.SYSTEM, AdminScope.PROJECT],
    }

    assert {
        role: [permission.value for permission in permissions]
        for role, permissions in ADMIN_ROLE_PERMISSIONS.items()
    } == expected_permissions
    assert {role: list(scopes) for role, scopes in ADMIN_ROLE_SCOPES.items()} == expected_scopes
    assert all(
        not permission.value.startswith("artifact.")
        for permission in ADMIN_ROLE_PERMISSIONS[AdminRole.AUDIT_AUTHORITY]
    )

    permission_response = AdminRoleGrantService.permission_definitions()
    role_response = AdminRoleGrantService.role_definitions()
    assert permission_response.total == 71
    assert [item.permission_id.value for item in permission_response.items] == sorted(
        permission.value for permission in PermissionId
    )
    assert role_response.total == 5
    assert [item.role for item in role_response.items] == list(AdminRole)
    assert [list(item.allowed_scopes) for item in role_response.items] == [
        expected_scopes[role] for role in AdminRole
    ]


async def test_definition_reads_authorize_touch_and_commit_before_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, object]] = []
    resolved = SimpleNamespace(profile=SimpleNamespace(id=str(uuid4())))

    class Session:
        async def commit(self) -> None:
            events.append(("commit", None))

        async def rollback(self) -> None:
            events.append(("rollback", None))

    class Authorization:
        async def require(self, action_id, resource):
            events.append(("authorize", (action_id, resource)))

    class ActorService:
        def __init__(self, session) -> None:
            assert session is test_session

        async def touch_after_authorization(self, actor) -> None:
            assert actor is resolved
            events.append(("touch", actor))

    test_session = Session()
    monkeypatch.setattr(authorization_router, "ActorService", ActorService)

    permissions = await authorization_router.read_permission_definitions(
        resolved,
        Authorization(),
        test_session,
    )
    roles = await authorization_router.read_admin_role_definitions(
        resolved,
        Authorization(),
        test_session,
    )

    first_action, first_resource = events[0][1]
    second_action, second_resource = events[3][1]
    assert first_action is ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ
    assert isinstance(first_resource, PermissionCatalogueResourceContext)
    assert first_resource.resource_id == "workstream:permission_catalogue"
    assert second_action is ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ
    assert isinstance(second_resource, AdminRoleDefinitionsResourceContext)
    assert second_resource.resource_id == "workstream:admin_role_definitions"
    assert [event for event, _ in events] == [
        "authorize",
        "touch",
        "commit",
        "authorize",
        "touch",
        "commit",
    ]
    assert permissions.total == len(PermissionId)
    assert roles.total == len(AdminRole)


@pytest.mark.parametrize(
    ("route", "action_id", "resource_type", "read_method"),
    [
        (
            authorization_router.read_actor_profile,
            ActionId.ACTOR_PROFILE_READ,
            ActorProfileAdminReadResourceContext,
            "read_admin_profile",
        ),
        (
            authorization_router.read_actor_identity_link,
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActorIdentityLinkAdminReadResourceContext,
            "read_admin_identity_link",
        ),
    ],
)
@pytest.mark.parametrize("self_target", [False, True])
async def test_actor_admin_routes_authorize_before_lookup_touch_and_commit(
    monkeypatch: pytest.MonkeyPatch,
    route,
    action_id: ActionId,
    resource_type,
    read_method: str,
    self_target: bool,
) -> None:
    target_id = uuid4()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(target_id if self_target else uuid4()),
            updated_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        ),
        identity_link=SimpleNamespace(last_verified_at=datetime.now(UTC)),
    )
    events: list[tuple[str, object]] = []

    class Response:
        def __init__(self) -> None:
            self.updates: list[dict] = []

        def model_copy(self, *, update):
            self.updates.append(update)
            return self

    response = Response()

    class Session:
        async def commit(self) -> None:
            events.append(("commit", None))

        async def rollback(self) -> None:
            events.append(("rollback", None))

    class Authorization:
        async def require(self, requested_action, resource):
            events.append(("authorize", (requested_action, resource)))

    class ActorService:
        def __init__(self, session) -> None:
            assert session is test_session

        async def read_admin_profile(self, actor_profile_id):
            assert read_method == "read_admin_profile"
            events.append(("lookup", actor_profile_id))
            return response

        async def read_admin_identity_link(self, actor_profile_id):
            assert read_method == "read_admin_identity_link"
            events.append(("lookup", actor_profile_id))
            return response

        async def touch_after_authorization(self, actor) -> None:
            assert actor is resolved
            events.append(("touch", actor))

    test_session = Session()
    monkeypatch.setattr(authorization_router, "ActorService", ActorService)

    result = await route(target_id, resolved, Authorization(), test_session)

    requested_action, resource = events[0][1]
    assert requested_action is action_id
    assert isinstance(resource, resource_type)
    assert resource.resource_id == target_id
    assert result is response
    assert [event for event, _ in events] == ["authorize", "lookup", "touch", "commit"]
    if not self_target:
        assert response.updates == []
    elif action_id is ActionId.ACTOR_PROFILE_READ:
        assert response.updates == [
            {
                "updated_at": resolved.profile.updated_at,
                "last_seen_at": resolved.profile.last_seen_at,
            }
        ]
    else:
        assert response.updates == [{"last_verified_at": resolved.identity_link.last_verified_at}]


@pytest.mark.parametrize(
    "route",
    [
        authorization_router.read_actor_profile,
        authorization_router.read_actor_identity_link,
    ],
)
async def test_actor_admin_missing_resource_rolls_back_without_touch_or_commit(
    monkeypatch: pytest.MonkeyPatch,
    route,
) -> None:
    events: list[str] = []

    class Session:
        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    class Authorization:
        async def require(self, _action_id, _resource):
            events.append("authorize")

    class ActorService:
        def __init__(self, _session) -> None:
            pass

        async def read_admin_profile(self, _actor_profile_id):
            events.append("lookup")
            return None

        async def read_admin_identity_link(self, _actor_profile_id):
            events.append("lookup")
            return None

        async def touch_after_authorization(self, _resolved) -> None:
            events.append("touch")

    monkeypatch.setattr(authorization_router, "ActorService", ActorService)

    with pytest.raises(StructuredHTTPException) as missing:
        await route(
            uuid4(),
            SimpleNamespace(),
            Authorization(),
            Session(),
        )

    assert missing.value.status_code == 404
    assert missing.value.error_code == "actor_resource_not_found"
    assert events == ["authorize", "lookup", "rollback"]


async def test_authorization_route_database_failures_rollback_and_map_to_retryable_503() -> None:
    class Session:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        async def commit(self) -> None:
            self.commits += 1
            raise SQLAlchemyError("commit failed")

        async def rollback(self) -> None:
            self.rollbacks += 1

    async def failed_operation() -> None:
        raise SQLAlchemyError("query failed")

    async def cancelled_operation() -> None:
        raise asyncio.CancelledError

    session = Session()
    with pytest.raises(StructuredHTTPException) as commit_failure:
        await authorization_router._commit_or_unavailable(session)
    with pytest.raises(StructuredHTTPException) as query_failure:
        await authorization_router._database_call(session, failed_operation())
    with pytest.raises(asyncio.CancelledError):
        await authorization_router._database_call(session, cancelled_operation())

    for failure in (commit_failure.value, query_failure.value):
        assert failure.status_code == 503
        assert failure.error_code == "service_unavailable"
        assert failure.retryable is True
    assert session.commits == 1
    assert session.rollbacks == 3


@pytest.mark.parametrize(
    ("outcome", "expected_error", "expected_events"),
    [
        ("success", None, ["reserve", "authorize", "touch", "complete", "commit"]),
        ("replay", None, ["reserve", "authorize", "touch", "commit"]),
        (
            "mismatch",
            "idempotency_mismatch",
            ["reserve", "authorize", "rollback", "record_mismatch", "commit"],
        ),
        (
            "conflict",
            "identity_link_already_revoked",
            [
                "reserve",
                "authorize",
                "touch",
                "complete",
                "rollback",
                "record_conflict",
                "commit",
            ],
        ),
        (
            "sql_failure",
            "service_unavailable",
            ["reserve", "authorize", "touch", "complete", "rollback"],
        ),
    ],
)
async def test_identity_link_lifecycle_route_preserves_outcome_transaction_contract(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_error: str | None,
    expected_events: list[str],
) -> None:
    """Prove route-owned ordering and stable mapping for every lifecycle outcome."""
    caller_id = uuid4()
    target_link_id = uuid4()
    target_actor_id = uuid4()
    idempotency_key = uuid4()
    events: list[str] = []
    response_reference = AuthorityResponseReference(
        resource_type=AuthorityResourceType.ACTOR_IDENTITY_LINK,
        resource_id=target_link_id,
        version=None,
        http_status=200,
    )
    response = IdentityLinkLifecycleMutationResponse(
        resource_type="actor_identity_link",
        resource_id=target_link_id,
        version=None,
        http_status=200,
    )
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=idempotency_key,
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(caller_id),
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
        request_digest=DIGEST,
    )
    reservation = {
        "success": ClaimedReservation(claim=claim),
        "replay": ReplayedReservation(response=response_reference),
        "mismatch": MismatchedReservation(),
        "conflict": ClaimedReservation(claim=claim),
        "sql_failure": ClaimedReservation(claim=claim),
    }[outcome]

    class Session:
        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    class Authorization:
        async def require(self, action_id, resource):
            events.append("authorize")
            assert action_id is ActionId.ACTOR_IDENTITY_LINK_REVOKE
            assert isinstance(resource, ActorIdentityLinkLifecycleResourceContext)
            assert resource.resource_id == target_link_id
            assert resource.transition == "revoke"
            assert resource.existing_idempotency_record is (outcome in {"replay", "mismatch"})
            return SimpleNamespace(revalidated=True)

    class RouteActorService:
        def __init__(self, session) -> None:
            assert session is test_session

        async def touch_after_authorization(self, resolved) -> None:
            assert resolved.profile.id == str(caller_id)
            events.append("touch")

    class RouteLifecycleService:
        def __init__(self, session) -> None:
            assert session is test_session

        async def reserve(self, **kwargs):
            events.append("reserve")
            assert kwargs["idempotency_key"] == idempotency_key
            assert kwargs["actor_profile_id"] == caller_id
            assert kwargs["request"].identity_link_id == target_link_id
            return reservation

        async def record_mismatch(self, **kwargs) -> None:
            events.append("record_mismatch")
            assert kwargs["actor_profile_id"] == caller_id

        async def complete(self, **kwargs):
            events.append("complete")
            assert kwargs["actor_profile_id"] == caller_id
            assert kwargs["reason"] == "Revoke exact identity link"
            if outcome == "conflict":
                raise IdentityLinkLifecycleConflict(
                    "identity_link_already_revoked",
                    target_actor_id,
                )
            if outcome == "sql_failure":
                raise SQLAlchemyError("lifecycle write failed")
            return response

        async def record_conflict(self, **kwargs) -> None:
            events.append("record_conflict")
            assert kwargs["target_actor_profile_id"] == target_actor_id
            assert kwargs["code"] == "identity_link_already_revoked"

    test_session = Session()
    monkeypatch.setattr(authorization_router, "ActorService", RouteActorService)
    monkeypatch.setattr(
        authorization_router,
        "IdentityLinkLifecycleService",
        RouteLifecycleService,
    )

    call = authorization_router._mutate_identity_link_lifecycle(
        identity_link_id=target_link_id,
        payload=ActorLifecycleBody(reason="Revoke exact identity link"),
        idempotency_key=idempotency_key,
        resolved=SimpleNamespace(profile=SimpleNamespace(id=str(caller_id))),
        authorization=Authorization(),
        session=test_session,  # type: ignore[arg-type]
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
        action=ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        transition="revoke",
    )
    if expected_error is None:
        assert await call == response
    else:
        with pytest.raises(StructuredHTTPException) as failure:
            await call
        assert failure.value.error_code == expected_error
        assert failure.value.status_code == (503 if outcome == "sql_failure" else 409)
        assert failure.value.retryable is (outcome == "sql_failure")
    assert events == expected_events


@pytest.mark.parametrize(
    "definitions, message",
    [
        (ACTION_DEFINITIONS[:-1], "incomplete"),
        (ACTION_DEFINITIONS[:-1] + (ACTION_DEFINITIONS[0],), "incomplete"),
        (ACTION_DEFINITIONS + (ACTION_DEFINITIONS[0],), "incomplete"),
        (
            tuple(
                ActionDefinition(
                    definition.action_id,
                    definition.permission_id,
                    ActionOwner.AUTH_ART_02D_OPERATOR,
                    definition.availability,
                )
                if definition.action_id is ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE
                else definition
                for definition in ACTION_DEFINITIONS
            ),
            "metadata mismatch",
        ),
        (
            tuple(
                ActionDefinition(
                    definition.action_id,
                    definition.permission_id,
                    definition.owner,
                    ActionAvailability.ACTIVE,
                )
                if definition.action_id is ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE
                else definition
                for definition in ACTION_DEFINITIONS
            ),
            "active action boundary mismatch",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    "unknown.permission",  # type: ignore[arg-type]
                    ActionOwner.AUTH_ART_06B,
                    ActionAvailability.PLANNED,
                ),
            ),
            "invalid row",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    "WS-ART-001-06B",  # type: ignore[arg-type]
                    ActionAvailability.PLANNED,
                ),
            ),
            "invalid row",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    "unknown.action",  # type: ignore[arg-type]
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    ActionOwner.AUTH_ART_06B,
                    ActionAvailability.PLANNED,
                ),
            ),
            "invalid row",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    "unknown.owner",  # type: ignore[arg-type]
                    ActionAvailability.PLANNED,
                ),
            ),
            "invalid row",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    ActionOwner.AUTH_ART_06B,
                    "unknown.availability",  # type: ignore[arg-type]
                ),
            ),
            "invalid row",
        ),
    ],
)
def test_action_catalogue_construction_fails_closed(
    definitions: tuple[ActionDefinition, ...],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _index_actions(definitions)


def test_action_catalogue_rejects_count_and_permission_partition_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(authorization_catalogue, "PERMISSION_IDS", frozenset())
        with pytest.raises(RuntimeError, match="catalogue count mismatch"):
            _index_actions(ACTION_DEFINITIONS)

    with monkeypatch.context() as patch:
        patch.setattr(authorization_catalogue, "HISTORICAL_PERMISSION_IDS", frozenset())
        with pytest.raises(RuntimeError, match="permission boundary mismatch"):
            _index_actions(ACTION_DEFINITIONS)


@pytest.mark.parametrize(
    "mutation",
    ["historical_owner", "wrong_custodian", "swapped_custodians", "mapping", "availability"],
)
def test_rev_custody_catalogue_mutations_fail_closed(mutation: str) -> None:
    definitions = list(ACTION_DEFINITIONS)
    first_index = next(
        index
        for index, definition in enumerate(definitions)
        if definition.action_id is ActionId.REVIEW_QUEUE_READ
    )
    second_index = next(
        index
        for index, definition in enumerate(definitions)
        if definition.action_id is ActionId.REVIEW_CLAIM
    )
    if mutation == "historical_owner":
        definitions[first_index] = replace(
            definitions[first_index],
            owner="WS-REV-001-05",  # type: ignore[arg-type]
        )
        message = "invalid row"
    elif mutation == "wrong_custodian":
        definitions[first_index] = replace(definitions[first_index], owner=ActionOwner.AUTH_REV_12)
        message = "metadata mismatch"
    elif mutation == "swapped_custodians":
        definitions[first_index] = replace(definitions[first_index], owner=ActionOwner.AUTH_REV_06)
        definitions[second_index] = replace(
            definitions[second_index], owner=ActionOwner.AUTH_REV_05
        )
        message = "metadata mismatch"
    elif mutation == "mapping":
        definitions[first_index] = replace(
            definitions[first_index], permission_id=PermissionId.REVIEW_QUEUE_INSPECT
        )
        message = "metadata mismatch"
    else:
        definitions[first_index] = replace(
            definitions[first_index], availability=ActionAvailability.ACTIVE
        )
        message = "active action boundary mismatch"

    with pytest.raises(RuntimeError, match=message):
        _index_actions(tuple(definitions))


def _runtime_context(
    *,
    actor_status: ActorStatus = ActorStatus.ACTIVE,
    link_status: IdentityLinkStatus = IdentityLinkStatus.ACTIVE,
    actor_kind: ActorKind = ActorKind.HUMAN,
    service_identity: ServiceIdentity = ServiceIdentity.ARTIFACT_VERIFIER,
) -> AuthorizationContext:
    context_type = (
        ServiceAuthorizationContext
        if actor_kind is ActorKind.SERVICE
        else HumanAuthorizationContext
    )
    service_fields = (
        {"service_identity": service_identity} if actor_kind is ActorKind.SERVICE else {}
    )
    return context_type(
        actor_profile_id=uuid4(),
        actor_kind=actor_kind,
        actor_status=actor_status,
        identity_link_id=uuid4(),
        identity_link_status=link_status,
        request_id=uuid4(),
        correlation_id=uuid4(),
        **service_fields,
    )


class _DecisionEvidence:
    def __init__(self) -> None:
        self.events: list[AuthorityAuditEventInput] = []

    async def add_authority_event(self, event: AuthorityAuditEventInput) -> None:
        self.events.append(event)


_DEFAULT_REVALIDATOR = object()


def _runtime_service(
    context: AuthorizationContext,
    *,
    session=None,
    admin_repository=None,
    revalidate=_DEFAULT_REVALIDATOR,
    revalidate_service=None,
) -> tuple[AuthorizationService, _DecisionEvidence]:
    if revalidate is _DEFAULT_REVALIDATOR:

        async def revalidate(current, _resource):
            return current

    service = AuthorizationService(
        session if session is not None else object(),  # type: ignore[arg-type]
        context,
        revalidate_actor_self=revalidate,
        revalidate_service=revalidate_service,
        admin_repository=admin_repository,
    )
    evidence = _DecisionEvidence()
    service._audit = evidence  # type: ignore[assignment]
    return service, evidence


class _PreparedTestSession:
    """Minimal stable-root session contract for capability unit tests."""

    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.nested = False
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return self.nested


@pytest.mark.asyncio
async def test_project_mutation_actions_cannot_issue_prepared_handles_while_planned() -> None:
    """Deny every 12A action before actor locks, evidence, or handle issuance."""
    context = _runtime_context()
    session = _PreparedTestSession()

    class UnexpectedFacts:
        def __getattr__(self, name: str):
            raise AssertionError(f"planned project mutation reached {name}")

    facts = UnexpectedFacts()
    authorization, evidence = _runtime_service(
        context,
        session=session,
        admin_repository=facts,
    )
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    project_id = uuid4()
    for action_id in PROJECT_MUTATION_RESOURCE_BY_ACTION:
        if action_id is ActionId.PROJECT_CREATE:
            continue
        scope = PreparedAuthorityScope(
            kind=(
                PreparedAuthorityScopeKind.SYSTEM
                if action_id is ActionId.PROJECT_CREATE
                else PreparedAuthorityScopeKind.PROJECT
            ),
            project_id=None if action_id is ActionId.PROJECT_CREATE else project_id,
        )
        with pytest.raises(PreparedAuthorizationUnsupported) as exc_info:
            await prepared.prepare(
                action_id,
                PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={}),
                scope,
            )
        assert exc_info.value.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE
    assert prepared._issued == {}
    assert evidence.events == []


class _ProjectCreateAuthorityFacts:
    def __init__(self, context: HumanAuthorizationContext, *, grant=None) -> None:
        self.context = context
        self.grant = grant

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        assert identity_link_id == self.context.identity_link_id
        assert actor_profile_id == self.context.actor_profile_id
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(
                id=str(actor_profile_id), actor_kind="human", status="active"
            ),
        )

    async def find_effective_grant(
        self,
        actor_profile_id,
        permission_id,
        *,
        scope_project_id,
        system_scope_only,
        for_update,
    ):
        assert actor_profile_id == self.context.actor_profile_id
        assert permission_id is PermissionId.PROJECT_CREATE
        assert scope_project_id is None
        assert system_scope_only is True
        assert for_update is True
        return self.grant


@pytest.mark.asyncio
async def test_project_create_prepared_authority_is_system_scoped_and_evidenced() -> None:
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    grant_id = uuid4()
    facts = _ProjectCreateAuthorityFacts(
        context, grant=SimpleNamespace(id=grant_id, status="active")
    )
    authorization, evidence = _runtime_service(
        context, session=session, admin_repository=facts
    )
    prepared = PreparedAuthorizationService(
        session, context, authorization, facts  # type: ignore[arg-type]
    )
    operation_id, project_id, key = uuid4(), uuid4(), uuid4()
    caller_input = PreparedAuthorizationInput(
        idempotency_key=key,
        request_value={
            "operation_id": str(operation_id),
            "project_id": str(project_id),
            "operation_generation": 1,
        },
    )
    handle = await prepared.prepare(
        ActionId.PROJECT_CREATE,
        caller_input,
        PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
    )
    decision = await prepared.consume(
        handle,
        ActionId.PROJECT_CREATE,
        caller_input,
        ProjectCreateResourceContext(
            resource_type="project_create",
            resource_id=operation_id,
            requested_project_id=project_id,
            operation_generation=1,
        ),
    )

    assert decision.allowed is True
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == grant_id
    assert decision.matched_scope_project_id is None
    assert evidence.events[0].after_facts == {
        "allowed": True,
        "resource_context_digest": decision.resource_context_digest,
    }
    assert evidence.events[0].resource_type == "project_create_operation"
    assert evidence.events[0].resource_id == str(operation_id)
    assert evidence.events[0].target_ref_kind == "project"
    assert evidence.events[0].target_ref_id == str(project_id)

    second = await prepared.prepare(
        ActionId.PROJECT_CREATE,
        caller_input,
        PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            second,
            ActionId.PROJECT_CREATE,
            caller_input,
            ProjectCreateResourceContext(
                resource_type="project_create",
                resource_id=uuid4(),
                requested_project_id=project_id,
                operation_generation=1,
            ),
        )


@pytest.mark.asyncio
async def test_project_create_preparation_denies_wrong_scope_missing_grant_and_service() -> None:
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    facts = _ProjectCreateAuthorityFacts(context)
    authorization, evidence = _runtime_service(
        context, session=session, admin_repository=facts
    )
    prepared = PreparedAuthorizationService(
        session, context, authorization, facts  # type: ignore[arg-type]
    )
    operation_id = uuid4()
    project_id = uuid4()
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(),
        request_value={
            "operation_id": str(operation_id),
            "project_id": str(project_id),
            "operation_generation": 1,
        },
    )
    with pytest.raises(PreparedAuthorizationUnsupported) as missing:
        await prepared.prepare(
            ActionId.PROJECT_CREATE,
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
    assert missing.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED

    with pytest.raises(PreparedAuthorizationUnsupported) as scoped:
        await prepared.prepare(
            ActionId.PROJECT_CREATE,
            caller_input,
            PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT, project_id=uuid4()
            ),
        )
    assert scoped.value.denial_code is AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
    assert evidence.events == []

    service_context = _runtime_context(actor_kind=ActorKind.SERVICE)
    service_authorization, _ = _runtime_service(
        service_context, session=session, admin_repository=object()
    )
    service_prepared = PreparedAuthorizationService(
        session,
        service_context,
        service_authorization,
        service_authorization._admin,
    )
    with pytest.raises(PreparedAuthorizationUnsupported) as service_denial:
        await service_prepared.prepare(
            ActionId.PROJECT_CREATE,
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
    assert service_denial.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED


class _ProjectReadAuthorityFacts:
    """Minimal grant repository used by project-read kernel tests."""

    def __init__(self, *, admin_grant=None, project_grant=None) -> None:
        self.admin_grant = admin_grant
        self.project_grant = project_grant

    async def find_effective_grant(self, *_args, **_kwargs):
        return self.admin_grant

    async def find_active_project_role_any(self, **_kwargs):
        return self.project_grant

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(
                id=str(actor_profile_id),
                actor_kind="human",
                status="active",
            ),
        )

    async def has_effective_permission_any_scope(self, *_args, **_kwargs):
        return False

    async def has_active_project_role_any_project(self, *_args, **_kwargs):
        return False


class _ContextProjectionFacts:
    async def effective_admin_roles_for_project(self, **_kwargs):
        return ("access_administrator", "project_manager")

    async def active_project_roles_for_actor(self, **_kwargs):
        return ("reviewer", "submitter")


class _ContextProjectionAuthorization:
    def __init__(self) -> None:
        self.calls = []

    async def require(self, action_id, resource):
        self.calls.append((action_id, resource))


@pytest.mark.asyncio
async def test_project_read_kernel_prefers_admin_and_records_project_role_authority() -> None:
    context = _runtime_context()
    project_id = uuid4()
    resource = ProjectReadResourceContext(
        resource_type="project",
        resource_id=project_id,
        scope_project_id=project_id,
        project_status="active",
    )
    admin_grant = SimpleNamespace(id=uuid4())
    service, _ = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(
            admin_grant=admin_grant,
            project_grant=SimpleNamespace(id=uuid4()),
        ),
    )
    decision = await service.require(ActionId.PROJECT_READ, resource)
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == admin_grant.id
    assert decision.matched_scope_project_id == project_id
    assert decision.revalidated is True

    project_grant = SimpleNamespace(id=uuid4())
    service, _ = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(project_grant=project_grant),
    )
    decision = await service.require(ActionId.PROJECT_READ, resource)
    assert decision.matched_authority_kind is MatchedAuthorityKind.PROJECT_ROLE_GRANT
    assert decision.matched_grant_id == project_grant.id
    assert decision.matched_scope_project_id == project_id

    missing = resource.model_copy(update={"project_exists": False, "project_status": None})
    service, evidence = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(admin_grant=admin_grant),
    )
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.PROJECT_READ, missing)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_NOT_FOUND
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_project_diagnostic_read_requires_exact_active_admin_grant_and_child() -> None:
    context = _runtime_context()
    project_id = uuid4()
    grant = SimpleNamespace(id=uuid4())
    resource = ProjectDiagnosticReadResourceContext(
        resource_type="project_diagnostic",
        resource_id=uuid4(),
        scope_project_id=project_id,
        guide_id=uuid4(),
        guide_version="v1",
        target_kind="sufficiency_report",
        project_exists=True,
        guide_exists=True,
        target_exists=True,
        target_binding_digest=f"sha256:{'b' * 64}",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=f"sha256:{'a' * 64}",
    )
    with pytest.raises(ValidationError, match="source_snapshot_hash"):
        ProjectDiagnosticReadResourceContext(
            **resource.model_dump(exclude={"source_snapshot_hash"}),
            source_snapshot_hash="malformed",
        )
    with pytest.raises(ValidationError, match="requires snapshot facts"):
        ProjectDiagnosticReadResourceContext(
            **resource.model_dump(exclude={"source_snapshot_id", "source_snapshot_hash"})
        )
    collection = ProjectDiagnosticReadResourceContext(
        **resource.model_dump(
            exclude={"source_snapshot_id", "source_snapshot_hash", "target_kind"},
        ),
        target_kind="sufficiency_report_collection",
    )
    assert collection.source_snapshot_id is None
    service, evidence = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant),
    )
    decision = await service.require(ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ, resource)
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == grant.id
    assert decision.matched_scope_project_id == project_id
    assert decision.revalidated is True
    assert decision.resource_context_digest == authorization_resource_digest(resource)
    assert len(evidence.events) == 1
    assert evidence.events[0].after_facts["resource_context_digest"] == (
        decision.resource_context_digest
    )

    service, _ = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant),
    )
    with pytest.raises(AuthorizationDenied) as wrong_kind:
        await service.require(
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
            resource.model_copy(update={"target_kind": "submission_artifact_policy"}),
        )
    assert wrong_kind.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED

    missing = resource.model_copy(
        update={
            "target_exists": False,
            "target_binding_digest": None,
            "source_snapshot_id": None,
            "source_snapshot_hash": None,
        }
    )
    service, denied_evidence = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant),
    )
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ, missing)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_NOT_FOUND
    assert denied_evidence.events[0].after_facts["resource_context_digest"] == (
        exc_info.value.decision.resource_context_digest
    )


@pytest.mark.asyncio
async def test_project_11c2_reads_require_exact_admin_context_and_role_allowlist() -> None:
    context = _runtime_context()
    project_id, guide_id, snapshot_id, effective_id = (uuid4() for _ in range(4))
    grant = SimpleNamespace(id=uuid4())
    policy = ProjectPolicyReadResourceContext(
        resource_type="project_policy_read",
        resource_id=effective_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        guide_status="active",
        target_kind="effective_policy",
        project_exists=True,
        project_status="active",
        guide_exists=True,
        target_exists=True,
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=f"sha256:{'a' * 64}",
        effective_policy_id=effective_id,
        effective_policy_hash=f"sha256:{'b' * 64}",
        effective_policy_status="approved",
        target_binding_digest=f"sha256:{'c' * 64}",
    )
    with pytest.raises(ValidationError, match="policy target existence"):
        ProjectPolicyReadResourceContext(
            **policy.model_dump(exclude={"guide_status"}),
            guide_status="draft",
        )
    service, policy_evidence = _runtime_service(
        context, admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant)
    )
    decision = await service.require(
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ, policy
    )
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == grant.id
    assert policy_evidence.events[0].after_facts["resource_context_digest"] == (
        decision.resource_context_digest
    )

    checker_policy = policy.model_copy(
        update={
            "resource_id": uuid4(),
            "target_kind": "pre_submit_checker_policy",
            "checker_policy_id": uuid4(),
            "checker_policy_status": "compiled",
            "checker_bundle_hash": f"sha256:{'e' * 64}",
        }
    )
    service, checker_evidence = _runtime_service(
        context, admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant)
    )
    checker_decision = await service.require(
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ, checker_policy
    )
    assert checker_evidence.events[0].after_facts["resource_context_digest"] == (
        checker_decision.resource_context_digest
    )

    missing_policy = policy.model_copy(
        update={
            "target_exists": False,
            "source_snapshot_id": None,
            "source_snapshot_hash": None,
            "effective_policy_id": None,
            "effective_policy_hash": None,
            "effective_policy_status": None,
            "target_binding_digest": None,
        }
    )
    service, denied_policy_evidence = _runtime_service(
        context, admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant)
    )
    with pytest.raises(AuthorizationDenied) as denied_policy:
        await service.require(
            ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ, missing_policy
        )
    assert denied_policy.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_NOT_FOUND
    assert denied_policy.value.decision.matched_grant_id == grant.id
    assert denied_policy.value.decision.matched_scope_project_id == project_id
    assert denied_policy_evidence.events[0].matched_grant_id == str(grant.id)
    assert denied_policy_evidence.events[0].project_id == str(project_id)
    assert denied_policy_evidence.events[0].after_facts["resource_context_digest"] == (
        denied_policy.value.decision.resource_context_digest
    )

    active = ProjectActiveGuideReadResourceContext(
        resource_type="project_active_guide_read",
        resource_id=guide_id,
        scope_project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        guide_status="active",
        project_exists=True,
        project_status="active",
        guide_exists=True,
        target_exists=True,
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=f"sha256:{'a' * 64}",
        sufficiency_report_id=uuid4(),
        sufficiency_report_status="passed",
        submission_artifact_policy_id=uuid4(),
        submission_artifact_policy_hash=f"sha256:{'b' * 64}",
        submission_artifact_policy_status="approved",
        effective_policy_id=effective_id,
        effective_policy_hash=f"sha256:{'c' * 64}",
        effective_policy_status="approved",
        pre_submit_checker_policy_id=uuid4(),
        pre_submit_checker_bundle_hash=f"sha256:{'d' * 64}",
        pre_submit_checker_policy_status="compiled",
        post_submit_checker_policy_id=uuid4(),
        post_submit_checker_policy_status="approved",
        review_policy_id=uuid4(),
        revision_policy_id=uuid4(),
        policy_binding_digest=f"sha256:{'d' * 64}",
    )

    class RoleRecordingFacts(_ProjectReadAuthorityFacts):
        allowed_roles = None

        async def find_effective_grant(self, *_args, **kwargs):
            self.allowed_roles = kwargs.get("allowed_roles")
            return self.admin_grant

    facts = RoleRecordingFacts(admin_grant=grant)
    service, evidence = _runtime_service(context, admin_repository=facts)
    active_decision = await service.require(ActionId.PROJECT_ACTIVE_GUIDE_READ, active)
    assert facts.allowed_roles == {
        AdminRole.OPERATOR,
        AdminRole.PROJECT_MANAGER,
        AdminRole.AUDIT_AUTHORITY,
    }
    assert evidence.events[0].after_facts["resource_context_digest"] == (
        active_decision.resource_context_digest
    )

    missing = active.model_copy(
        update={
            "target_exists": False,
            "source_snapshot_id": None,
            "source_snapshot_hash": None,
            "policy_binding_digest": None,
        }
    )
    service, denied_evidence = _runtime_service(
        context, admin_repository=_ProjectReadAuthorityFacts(admin_grant=grant)
    )
    with pytest.raises(AuthorizationDenied) as denied:
        await service.require(ActionId.PROJECT_ACTIVE_GUIDE_READ, missing)
    assert denied.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_NOT_FOUND
    assert denied.value.decision.matched_grant_id == grant.id
    assert denied.value.decision.matched_scope_project_id == project_id
    assert denied_evidence.events[0].matched_grant_id == str(grant.id)
    assert denied_evidence.events[0].project_id == str(project_id)
    assert denied_evidence.events[0].after_facts["resource_context_digest"] == (
        denied.value.decision.resource_context_digest
    )


@pytest.mark.asyncio
async def test_actor_authorization_context_is_self_only_and_revalidated() -> None:
    context = _runtime_context()
    resource = ActorAuthorizationContextResourceContext(
        resource_type="actor_authorization_context",
        resource_id=context.actor_profile_id,
        scope_project_id=uuid4(),
        project_status="active",
    )
    service, _ = _runtime_service(
        context,
        admin_repository=_ProjectReadAuthorityFacts(project_grant=SimpleNamespace(id=uuid4())),
    )
    decision = await service.require(ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ, resource)
    assert decision.matched_authority_kind is MatchedAuthorityKind.PROJECT_ROLE_GRANT
    assert decision.matched_scope_project_id == resource.scope_project_id
    assert decision.revalidated is True

    service, _ = _runtime_service(context, admin_repository=_ProjectReadAuthorityFacts())
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ, resource)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED

    service, _ = _runtime_service(context, admin_repository=_ProjectReadAuthorityFacts())
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(
            ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
            resource.model_copy(update={"resource_id": uuid4()}),
        )
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED


@pytest.mark.asyncio
async def test_context_projection_excludes_planned_and_unrelated_actions() -> None:
    actor_id, project_id = uuid4(), uuid4()
    authorization = _ContextProjectionAuthorization()
    service = ActorAuthorizationContextReadService(
        authorization,  # type: ignore[arg-type]
        _ContextProjectionFacts(),  # type: ignore[arg-type]
    )
    response = await service.read(
        resolved=SimpleNamespace(profile=SimpleNamespace(id=str(actor_id), status="active")),
        project=SimpleNamespace(id=str(project_id), status="active"),
        project_selector_id=project_id,
    )
    assert len(authorization.calls) == 1
    assert authorization.calls[0][0] is ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ
    assert response.admin_roles == ("project_manager",)
    assert response.project_roles == ("reviewer", "submitter")
    assert response.effective_action_ids == (
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
    )
    archived = await service.read(
        resolved=SimpleNamespace(profile=SimpleNamespace(id=str(actor_id), status="active")),
        project=SimpleNamespace(id=str(project_id), status="archived"),
        project_selector_id=project_id,
    )
    assert archived.effective_action_ids == (
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        ActionId.PROJECT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
    )

    class FinanceProjectionFacts:
        async def effective_admin_roles_for_project(self, **_kwargs):
            return ("finance_authority",)

        async def active_project_roles_for_actor(self, **_kwargs):
            return ("submitter",)

    finance = ActorAuthorizationContextReadService(
        authorization,  # type: ignore[arg-type]
        FinanceProjectionFacts(),  # type: ignore[arg-type]
    )
    finance_response = await finance.read(
        resolved=SimpleNamespace(profile=SimpleNamespace(id=str(actor_id), status="active")),
        project=SimpleNamespace(id=str(project_id), status="active"),
        project_selector_id=project_id,
    )
    assert ActionId.PROJECT_ACTIVE_GUIDE_READ not in finance_response.effective_action_ids
    assert ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ not in (
        finance_response.effective_action_ids
    )
    assert finance_response.effective_action_ids == (ActionId.PROJECT_READ,)


class _PreparedActorFacts:
    def __init__(self, context: HumanAuthorizationContext) -> None:
        self.context = context
        self.calls = 0

    async def lock_actor_self(self, actor_profile_id, identity_link_id):
        self.calls += 1
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
        )


class _PreparedAdminFacts(_PreparedActorFacts):
    def __init__(self, context: HumanAuthorizationContext) -> None:
        super().__init__(context)
        self.grant_id = uuid4()
        self.control_calls = 0
        self.grant_calls = 0
        self.grant_requests: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.target_calls = 0

    async def lock_control(self):
        self.control_calls += 1
        return SimpleNamespace(id=1)

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return await self.lock_actor_self(actor_profile_id, identity_link_id)

    async def find_effective_grant(self, *args, **kwargs):
        self.grant_calls += 1
        self.grant_requests.append((args, kwargs))
        return SimpleNamespace(id=self.grant_id, status="active")

    async def lock_eligible_human(self, actor_profile_id):
        self.target_calls += 1
        return (
            SimpleNamespace(id=str(uuid4()), actor_profile_id=str(actor_profile_id)),
            SimpleNamespace(id=str(actor_profile_id)),
        )

    async def project_exists(self, _project_id, *, for_update=False):
        return True

    async def get_grant(self, grant_id, *, for_update=False):
        assert for_update is True
        return SimpleNamespace(
            id=grant_id,
            status="active",
            target_actor_profile_id=str(uuid4()),
        )

    async def lock_actor_lifecycle_target(self, actor_profile_id):
        return SimpleNamespace(id=actor_profile_id)

    async def lock_identity_link_lifecycle_target(self, identity_link_id):
        return SimpleNamespace(id=identity_link_id)


@pytest.mark.asyncio
async def test_project_role_reads_use_exact_scope_and_candidate_kernel_guard() -> None:
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    facts = _PreparedAdminFacts(context)
    project_id = uuid4()
    service, evidence = _runtime_service(context, admin_repository=facts)

    decision = await service.require(
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ProjectRoleGrantCollectionResourceContext(
            resource_type="project_role_grant_collection",
            resource_id=project_id,
            scope_project_id=project_id,
            project_status="archived",
        ),
    )
    assert decision.allowed is True
    assert decision.matched_scope_project_id == project_id
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT

    detail = await service.require(
        ActionId.PROJECT_ROLE_GRANT_READ,
        ProjectRoleGrantReadResourceContext(
            resource_type="project_role_grant",
            resource_id=uuid4(),
            scope_project_id=project_id,
            project_status="archived",
        ),
    )
    assert detail.allowed is True

    for project_status in ("draft", "active", "paused"):
        candidate = await service.require(
            ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
            ProjectContributorCandidateCollectionResourceContext(
                resource_type="project_contributor_candidate_collection",
                resource_id=project_id,
                scope_project_id=project_id,
                project_status=project_status,
            ),
        )
        assert candidate.allowed is True

    for project_status in ("draft", "active", "paused", "archived"):
        history = await service.require(
            ActionId.PROJECT_ROLE_GRANT_LIST,
            ProjectRoleGrantCollectionResourceContext(
                resource_type="project_role_grant_collection",
                resource_id=project_id,
                scope_project_id=project_id,
                project_status=project_status,
            ),
        )
        assert history.allowed is True

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(
            ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
            ProjectContributorCandidateCollectionResourceContext(
                resource_type="project_contributor_candidate_collection",
                resource_id=project_id,
                scope_project_id=project_id,
                project_status="archived",
            ),
        )
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert evidence.events[-1].denial_code == "resource_guard_denied"


@pytest.mark.parametrize(
    "action_id",
    [
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
    ],
)
@pytest.mark.parametrize(
    "denial_code",
    [
        AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED,
        AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
    ],
)
def test_project_role_read_denials_share_one_public_concealment(
    action_id: ActionId,
    denial_code: AuthorizationDenialCode,
) -> None:
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        allowed=False,
        action_id=action_id,
        permission_id=ACTION_BY_ID[action_id].permission_id,
        resource_type="project_role_grant_collection",
        resource_id=uuid4(),
        resource_context_digest=DIGEST,
        denial_code=denial_code,
        matched_authority_kind=None,
        matched_grant_id=None,
        matched_scope_project_id=None,
        revalidated=False,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    translated = authorization_http_error(AuthorizationDenied(decision))
    assert translated.status_code == 404
    assert translated.error_code == "project_authorization_resource_not_found"


@pytest.mark.parametrize(
    "denial_code",
    [
        AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED,
        AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        AuthorizationDenialCode.ACTOR_NOT_FOUND,
        AuthorizationDenialCode.GRANT_NOT_FOUND,
    ],
)
def test_project_role_mutation_denials_share_resource_not_found_concealment(
    denial_code: AuthorizationDenialCode,
) -> None:
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        allowed=False,
        action_id=ActionId.PROJECT_ROLE_GRANT_ISSUE,
        permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        resource_type="project_role_grant",
        resource_id=uuid4(),
        resource_context_digest=DIGEST,
        denial_code=denial_code,
        matched_authority_kind=None,
        matched_grant_id=None,
        matched_scope_project_id=None,
        revalidated=False,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    translated = authorization_router._project_role_mutation_denial(AuthorizationDenied(decision))
    assert translated.status_code == 404
    assert translated.error_code == "resource_not_found"
    assert translated.error_message == "Resource not found"


def test_project_role_read_permissions_separate_manager_and_auditor_authority() -> None:
    assert PermissionId.PROJECT_ROLE_GRANT_READ in ADMIN_ROLE_PERMISSIONS[AdminRole.PROJECT_MANAGER]
    assert (
        PermissionId.PROJECT_ROLE_GRANT_MANAGE in ADMIN_ROLE_PERMISSIONS[AdminRole.PROJECT_MANAGER]
    )


def test_project_read_projection_permissions_have_exact_admin_role_matrix() -> None:
    permissions = {
        PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ,
        PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
    }
    for role in (AdminRole.PROJECT_MANAGER, AdminRole.OPERATOR, AdminRole.AUDIT_AUTHORITY):
        assert permissions <= set(ADMIN_ROLE_PERMISSIONS[role])
    for role in (AdminRole.FINANCE_AUTHORITY, AdminRole.ACCESS_ADMINISTRATOR):
        assert permissions.isdisjoint(ADMIN_ROLE_PERMISSIONS[role])
    assert PermissionId.PROJECT_ROLE_GRANT_READ in ADMIN_ROLE_PERMISSIONS[AdminRole.AUDIT_AUTHORITY]
    assert (
        PermissionId.PROJECT_ROLE_GRANT_MANAGE
        not in ADMIN_ROLE_PERMISSIONS[AdminRole.AUDIT_AUTHORITY]
    )


@pytest.mark.asyncio
async def test_prepared_actor_self_handle_is_exact_single_use_and_transaction_bound():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedActorFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(),
        request_value={"display_name": "Prepared"},
    )
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.ACTOR_SELF,
        actor_profile_id=context.actor_profile_id,
    )
    with pytest.raises(TypeError, match="invalid prepared authorization consumer"):
        await authorization._prepare_prelocked(object(), ActionId.ACTOR_PROFILE_UPDATE_SELF, scope)
    assert facts.calls == 0
    handle = await prepared.prepare(ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, scope)
    sealed = prepared._issued[handle].authority  # type: ignore[union-attr]
    with pytest.raises(AttributeError):
        sealed.matched_grant_status = "active"
    assert not hasattr(authorization, "_seal_prelocked")
    assert repr(handle) == "<PreparedAuthorizationHandle>"
    assert facts.calls == 1

    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle,
            ActionId.ACTOR_PROFILE_READ_SELF,
            caller_input,
            ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=("display_name",),
            ),
        )
    assert evidence.events == []

    decision = await prepared.consume(
        handle,
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        caller_input,
        ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=context.actor_profile_id,
            requested_fields=("display_name",),
        ),
    )
    assert decision.allowed is True
    assert len(evidence.events) == 1
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            caller_input,
            ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=("display_name",),
            ),
        )


@pytest.mark.asyncio
async def test_prepared_binding_mismatch_does_not_consume_valid_handle():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    facts = _PreparedActorFacts(context)
    authorization, evidence = _runtime_service(context, session=session)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    idempotency_key = uuid4()
    original = PreparedAuthorizationInput(idempotency_key=idempotency_key, request_value={"v": 1})
    handle = await prepared.prepare(
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        original,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ACTOR_SELF,
            actor_profile_id=context.actor_profile_id,
        ),
    )
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=("contact_email",),
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            PreparedAuthorizationInput(idempotency_key=idempotency_key, request_value={"v": 2}),
            resource,
        )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={"v": 1}),
            resource,
        )
    assert evidence.events == []

    decision = await prepared.consume(
        handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, original, resource
    )
    assert decision.allowed is True

    stale = await prepared.prepare(
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        original,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ACTOR_SELF,
            actor_profile_id=context.actor_profile_id,
        ),
    )
    session.root = SimpleNamespace(is_active=True)
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(stale, ActionId.ACTOR_PROFILE_UPDATE_SELF, original, resource)


@pytest.mark.asyncio
async def test_prepared_rejects_cross_context_service_session_and_concurrent_consume():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    facts = _PreparedActorFacts(context)
    authorization, evidence = _runtime_service(context, session=session)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    other_context = context.model_copy(
        update={"actor_profile_id": uuid4(), "identity_link_id": uuid4()}
    )
    with pytest.raises(TypeError, match="invalid prepared authorization composition"):
        PreparedAuthorizationService(
            session,  # type: ignore[arg-type]
            other_context,
            authorization,
            facts,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="one exact session"):
        PreparedAuthorizationService(
            _PreparedTestSession(),  # type: ignore[arg-type]
            context,
            authorization,
            facts,  # type: ignore[arg-type]
        )

    sibling = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={})
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.ACTOR_SELF,
        actor_profile_id=context.actor_profile_id,
    )
    handle = await prepared.prepare(ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, scope)
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=("display_name",),
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await sibling.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)
    outcomes = await asyncio.gather(
        prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource),
        prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource),
        return_exceptions=True,
    )
    assert sum(isinstance(item, AuthorizationDecision) for item in outcomes) == 1
    assert sum(isinstance(item, PreparedAuthorizationHandleInvalid) for item in outcomes) == 1
    assert len(evidence.events) == 1


def test_prepared_handle_rejects_construction_and_serializable_inputs():
    with pytest.raises(TypeError):
        PreparedAuthorizationHandle()
    with pytest.raises(ValidationError):
        PreparedAuthorizationInput(
            idempotency_key=uuid4(),
            request_value={"not_json": object()},  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_prepared_handle_rejects_forgery_copy_serialization_and_nested_roots():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    facts = _PreparedActorFacts(context)
    authorization, _ = _runtime_service(context, session=session)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"display_name": "opaque"}
    )
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.ACTOR_SELF,
        actor_profile_id=context.actor_profile_id,
    )
    handle = await prepared.prepare(ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, scope)
    forged = object.__new__(PreparedAuthorizationHandle)
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=("display_name",),
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(forged, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)
    with pytest.raises(copy.Error):
        copy.copy(handle)
    with pytest.raises(copy.Error):
        copy.deepcopy(handle)
    with pytest.raises(TypeError):
        pickle.dumps(handle)
    with pytest.raises(TypeError):
        json.dumps(handle)
    with pytest.raises(AttributeError):
        handle.capability = "leak"  # type: ignore[attr-defined]

    session.nested = True
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)

    forged_authority = object.__new__(authorization_kernel._PrelockedAuthority)
    with pytest.raises(TypeError, match="invalid prelocked authority"):
        await authorization._require_prelocked(
            prepared._consumer_token,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            resource,
            forged_authority,
        )
    session.nested = False
    prepared.close()
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)


@pytest.mark.asyncio
async def test_prepared_admin_consume_reuses_exact_locked_grant_without_requery():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"role": "project_manager"}
    )
    scope = PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
    handle = await prepared.prepare(ActionId.ADMIN_ROLE_GRANT_ISSUE, caller_input, scope)
    assert (facts.control_calls, facts.calls, facts.grant_calls) == (1, 1, 1)
    target_id = uuid4()
    decision = await prepared.consume(
        handle,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        caller_input,
        AdminRoleGrantIssueResourceContext(
            resource_type="admin_role_grant_issue",
            resource_id=target_id,
            role=AdminRole.ACCESS_ADMINISTRATOR,
            scope_type=AdminScope.SYSTEM,
        ),
    )
    assert decision.allowed is True
    assert decision.matched_grant_id == facts.grant_id
    assert (facts.control_calls, facts.calls, facts.grant_calls) == (1, 1, 1)
    assert facts.target_calls == 1
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_prepared_guide_ingest_binds_exact_project_and_locked_manager_grant():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    project_id = uuid4()
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"project_id": str(project_id)}
    )
    handle = await prepared.prepare(
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        caller_input,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=project_id,
        ),
    )
    assert (facts.calls, facts.grant_calls) == (1, 1)
    assert facts.grant_requests == [
        (
            (context.actor_profile_id, PermissionId.ARTIFACT_GUIDE_SOURCE_INGEST),
            {"scope_project_id": project_id, "for_update": True},
        )
    ]

    def resource(scope_project_id: UUID) -> GuideSourceIngestResourceContext:
        return GuideSourceIngestResourceContext(
            resource_type="project",
            resource_id=scope_project_id,
            scope_project_id=scope_project_id,
            guide_id=uuid4(),
            guide_source_snapshot_id=uuid4(),
            guide_source_item_id=uuid4(),
            operation_identity="sha256:" + "b" * 64,
            request_digest="sha256:" + "c" * 64,
            sha256="sha256:" + "d" * 64,
            byte_count=17,
            media_type="application/octet-stream",
        )

    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(
            handle,
            ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
            caller_input,
            resource(uuid4()),
        )
    assert evidence.events == []
    decision = await prepared.consume(
        handle,
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        caller_input,
        resource(project_id),
    )
    assert decision.allowed is True
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == facts.grant_id
    assert decision.matched_scope_project_id == project_id
    assert (facts.calls, facts.grant_calls) == (1, 1)
    assert len(evidence.events) == 1
    assert evidence.events[0].project_id == str(project_id)
    assert evidence.events[0].after_facts is not None
    assert evidence.events[0].after_facts["resource_context_digest"] == (
        decision.resource_context_digest
    )


@pytest.mark.asyncio
async def test_prepared_project_scope_rejects_system_and_other_project_without_consuming():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={})
    project_id = uuid4()
    handle = await prepared.prepare(
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        caller_input,
        PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=project_id),
    )
    for wrong_project in (None, uuid4()):
        wrong_resource = AdminRoleGrantIssueResourceContext(
            resource_type="admin_role_grant_issue",
            resource_id=uuid4(),
            role=AdminRole.PROJECT_MANAGER,
            scope_type=(AdminScope.SYSTEM if wrong_project is None else AdminScope.PROJECT),
            scope_project_id=wrong_project,
        )
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(
                handle,
                ActionId.ADMIN_ROLE_GRANT_ISSUE,
                caller_input,
                wrong_resource,
            )
    assert evidence.events == []
    allowed = await prepared.consume(
        handle,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        caller_input,
        AdminRoleGrantIssueResourceContext(
            resource_type="admin_role_grant_issue",
            resource_id=uuid4(),
            role=AdminRole.PROJECT_MANAGER,
            scope_type=AdminScope.PROJECT,
            scope_project_id=project_id,
        ),
    )
    assert allowed.matched_scope_project_id == project_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action_id", "resource"),
    [
        (
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            AdminRoleGrantResourceContext(resource_type="admin_role_grant", resource_id=uuid4()),
        ),
        (
            ActionId.ACTOR_SERVICE_PROVISION,
            ServiceActorProvisionResourceContext(
                resource_type="service_actor_provisioning",
                resource_id=ServiceIdentity.ARTIFACT_VERIFIER,
            ),
        ),
        *[
            (
                action_id,
                ActorProfileLifecycleResourceContext(
                    resource_type="actor_profile",
                    resource_id=uuid4(),
                    transition=transition,
                ),
            )
            for action_id, transition in (
                (ActionId.ACTOR_PROFILE_SUSPEND, "suspend"),
                (ActionId.ACTOR_PROFILE_REACTIVATE, "reactivate"),
                (ActionId.ACTOR_PROFILE_DEACTIVATE, "deactivate"),
            )
        ],
        *[
            (
                action_id,
                ActorIdentityLinkLifecycleResourceContext(
                    resource_type="actor_identity_link",
                    resource_id=uuid4(),
                    transition=transition,
                ),
            )
            for action_id, transition in (
                (ActionId.ACTOR_IDENTITY_LINK_REVOKE, "revoke"),
                (ActionId.ACTOR_IDENTITY_LINK_REACTIVATE, "reactivate"),
            )
        ],
    ],
)
async def test_prepared_supports_every_remaining_admin_lock_plan(action_id, resource):
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"action": action_id.value}
    )
    handle = await prepared.prepare(
        action_id,
        caller_input,
        PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
    )
    decision = await prepared.consume(handle, action_id, caller_input, resource)
    assert decision.allowed is True
    assert decision.action_id is action_id
    assert decision.matched_grant_id == facts.grant_id
    assert facts.control_calls == facts.grant_calls == 1
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_prepared_exact_consume_remains_spent_after_cancellation():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    facts = _PreparedActorFacts(context)
    authorization, _ = _runtime_service(context, session=session)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"display_name": "cancel"}
    )
    handle = await prepared.prepare(
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        caller_input,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ACTOR_SELF,
            actor_profile_id=context.actor_profile_id,
        ),
    )
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def wait_during_evaluation(*_args):
        entered.set()
        await blocked.wait()

    authorization._require_prelocked = wait_during_evaluation  # type: ignore[method-assign]
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=("display_name",),
    )
    task = asyncio.create_task(
        prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.consume(handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource)


@pytest.mark.asyncio
async def test_prepared_fixed_service_rejects_generic_scope_before_actor_lock():
    context = _runtime_context(actor_kind=ActorKind.SERVICE)
    assert isinstance(context, ServiceAuthorizationContext)

    class ServiceFacts:
        calls = 0

        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            self.calls += 1
            return (
                SimpleNamespace(
                    id=str(identity_link_id),
                    actor_profile_id=str(actor_profile_id),
                    status="active",
                ),
                SimpleNamespace(
                    id=str(actor_profile_id),
                    actor_kind="service",
                    status="active",
                    service_identity=context.service_identity.value,
                ),
            )

    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = ServiceFacts()
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    with pytest.raises(PreparedAuthorizationUnsupported) as exc_info:
        await prepared.prepare(
            ActionId.ARTIFACT_VERIFICATION_EXECUTE,
            PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={}),
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
    assert exc_info.value.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert facts.calls == 0
    assert evidence.events == []


@pytest.mark.parametrize(
    ("action_id", "service_identity"),
    tuple(
        (
            action_id,
            identity,
        )
        for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items()
        for action_id in actions
        if ACTION_BY_ID[action_id].availability is ActionAvailability.PLANNED
    ),
)
@pytest.mark.asyncio
async def test_project_setup_service_matrix_issues_no_handle_for_planned_actions(
    action_id: ActionId,
    service_identity: ServiceIdentity | None,
):
    context = _runtime_context(
        actor_kind=ActorKind.SERVICE if service_identity is not None else ActorKind.HUMAN,
        service_identity=service_identity or ServiceIdentity.ARTIFACT_VERIFIER,
    )

    class LockedFacts:
        calls = 0

        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            self.calls += 1
            return (
                SimpleNamespace(
                    id=str(identity_link_id),
                    actor_profile_id=str(actor_profile_id),
                    status="active",
                ),
                SimpleNamespace(
                    id=str(actor_profile_id),
                    actor_kind=context.actor_kind.value,
                    status="active",
                    service_identity=(
                        service_identity.value if service_identity is not None else None
                    ),
                ),
            )

    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = LockedFacts()
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    with pytest.raises(PreparedAuthorizationUnsupported) as exc_info:
        await prepared.prepare(
            action_id,
            PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={}),
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
    assert exc_info.value.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE
    assert facts.calls == 0
    assert prepared._issued == {}
    assert evidence.events == []


@pytest.mark.parametrize(
    ("action_id", "owning_identity"),
    tuple(
        (action_id, identity)
        for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items()
        for action_id in actions
        if ACTION_BY_ID[action_id].availability is ActionAvailability.PLANNED
    ),
)
@pytest.mark.asyncio
async def test_project_setup_service_matrix_wrong_identity_denies_before_availability(
    action_id: ActionId,
    owning_identity: ServiceIdentity,
):
    wrong_identity = next(
        identity
        for identity in ServiceIdentity
        if identity is not owning_identity
        and action_id not in SERVICE_ACTIONS_BY_IDENTITY.get(identity, frozenset())
    )
    context = _runtime_context(
        actor_kind=ActorKind.SERVICE,
        service_identity=wrong_identity,
    )
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,
    )

    with pytest.raises(PreparedAuthorizationUnsupported) as exc_info:
        await prepared.prepare(
            action_id,
            PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={}),
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )

    assert exc_info.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    assert facts.calls == 0
    assert prepared._issued == {}
    assert evidence.events == []


@pytest.mark.asyncio
async def test_prepared_rejects_unsupported_scope_missing_grant_and_inactive_root():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, _ = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    caller_input = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={})
    with pytest.raises(PreparedAuthorizationUnsupported):
        await prepared.prepare(
            ActionId.ACTOR_PROFILE_SUSPEND,
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=uuid4()),
        )
    with pytest.raises(PreparedAuthorizationUnsupported):
        await prepared.prepare(
            "unknown",  # type: ignore[arg-type]
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )

    async def missing_grant(*_args, **_kwargs):
        return None

    facts.find_effective_grant = missing_grant  # type: ignore[method-assign]
    with pytest.raises(PreparedAuthorizationUnsupported):
        await prepared.prepare(
            ActionId.ADMIN_ROLE_GRANT_ISSUE,
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
    session.root.is_active = False
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            caller_input,
            PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.ACTOR_SELF,
                actor_profile_id=context.actor_profile_id,
            ),
        )


@pytest.mark.asyncio
async def test_prepared_postgresql_failure_and_cancellation_are_atomic(
    authorization_factory,
) -> None:
    """Real caller transactions roll back participant/evidence and spend handles."""
    profile_id, link_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as session:
        session.add_all(
            [
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(profile_id),
                ),
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"prepared-failure-{profile_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(profile_id),
                    last_verified_at=now,
                ),
            ]
        )
        await session.commit()
        await session.execute(
            text(
                "create temporary table prepared_failure_participant (id int primary key, value int)"
            )
        )
        await session.execute(text("insert into prepared_failure_participant values (1, 0)"))
        await session.commit()
        context = HumanAuthorizationContext(
            actor_profile_id=profile_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        repository = AdminAuthorizationRepository(session)
        authorization = AuthorizationService(session, context, admin_repository=repository)
        prepared = PreparedAuthorizationService(
            session,
            context,
            authorization,
            repository,
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ACTOR_SELF,
            actor_profile_id=profile_id,
        )
        resource = ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=profile_id,
            requested_fields=("display_name",),
        )

        async def assert_handle_burned_without_reentry(
            handle: PreparedAuthorizationHandle,
            caller_input: PreparedAuthorizationInput,
        ) -> None:
            require_calls = 0
            evidence_calls = 0
            original_require = authorization._require_prelocked
            original_add_event = authorization._audit.add_authority_event

            async def counted_require(*args, **kwargs):
                nonlocal require_calls
                require_calls += 1
                return await original_require(*args, **kwargs)

            async def counted_add_event(event):
                nonlocal evidence_calls
                evidence_calls += 1
                return await original_add_event(event)

            authorization._require_prelocked = counted_require  # type: ignore[method-assign]
            authorization._audit.add_authority_event = counted_add_event  # type: ignore[method-assign]
            try:
                with pytest.raises(PreparedAuthorizationHandleInvalid):
                    await prepared.consume(
                        handle,
                        ActionId.ACTOR_PROFILE_UPDATE_SELF,
                        caller_input,
                        resource,
                    )
            finally:
                authorization._require_prelocked = original_require  # type: ignore[method-assign]
                authorization._audit.add_authority_event = original_add_event  # type: ignore[method-assign]
            assert require_calls == 0
            assert evidence_calls == 0

        success_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "commit"}
        )
        await session.begin()
        success_handle = await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF, success_input, scope
        )
        success_decision = await prepared.consume(
            success_handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            success_input,
            resource,
        )
        await session.execute(text("update prepared_failure_participant set value=1 where id=1"))
        await session.commit()
        assert (
            await session.scalar(text("select value from prepared_failure_participant where id=1"))
            == 1
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(success_decision.decision_id)},
            )
            == 1
        )
        await session.execute(text("update prepared_failure_participant set value=0 where id=1"))
        await session.commit()

        participant_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "participant"}
        )
        await session.begin()
        participant_handle = await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF, participant_input, scope
        )
        participant_decision = await prepared.consume(
            participant_handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            participant_input,
            resource,
        )
        await session.execute(text("update prepared_failure_participant set value=1 where id=1"))
        try:
            raise RuntimeError("injected participant failure")
        except RuntimeError:
            await session.rollback()
        assert (
            await session.scalar(text("select value from prepared_failure_participant where id=1"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(participant_decision.decision_id)},
            )
            == 0
        )
        await session.rollback()
        await assert_handle_burned_without_reentry(participant_handle, participant_input)

        evidence_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "evidence"}
        )
        await session.begin()
        evidence_handle = await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF, evidence_input, scope
        )

        class FailingEvidence:
            async def add_authority_event(self, _event):
                raise SQLAlchemyError("injected evidence failure")

        original_audit = authorization._audit
        authorization._audit = FailingEvidence()  # type: ignore[assignment]
        with pytest.raises(AuthorizationEvidenceUnavailable):
            await prepared.consume(
                evidence_handle,
                ActionId.ACTOR_PROFILE_UPDATE_SELF,
                evidence_input,
                resource,
            )
        await session.rollback()
        authorization._audit = original_audit
        await assert_handle_burned_without_reentry(evidence_handle, evidence_input)

        cancellation_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "cancellation"}
        )
        entered = asyncio.Event()
        blocked = asyncio.Event()
        issued_holder = {}

        async def cancelled_command():
            try:
                await session.begin()
                issued_holder["handle"] = await prepared.prepare(
                    ActionId.ACTOR_PROFILE_UPDATE_SELF, cancellation_input, scope
                )
                entered.set()
                await blocked.wait()
            except BaseException:
                await session.rollback()
                raise

        cancellation_task = asyncio.create_task(cancelled_command())
        await asyncio.wait_for(entered.wait(), timeout=5)
        cancellation_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancellation_task
        assert await session.scalar(text("select 1")) == 1
        await session.rollback()
        await assert_handle_burned_without_reentry(
            issued_holder["handle"],
            cancellation_input,
        )

        commit_failure_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "commit_failure"}
        )
        await session.begin()
        commit_failure_handle = await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF, commit_failure_input, scope
        )
        commit_failure_decision = await prepared.consume(
            commit_failure_handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            commit_failure_input,
            resource,
        )
        await session.execute(text("update prepared_failure_participant set value=2 where id=1"))
        original_commit = session.commit

        async def fail_commit():
            raise SQLAlchemyError("injected commit failure")

        session.commit = fail_commit  # type: ignore[method-assign]
        with pytest.raises(SQLAlchemyError):
            await session.commit()
        session.commit = original_commit  # type: ignore[method-assign]
        await session.rollback()
        assert (
            await session.scalar(text("select value from prepared_failure_participant where id=1"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(commit_failure_decision.decision_id)},
            )
            == 0
        )
        await session.rollback()
        await assert_handle_burned_without_reentry(
            commit_failure_handle,
            commit_failure_input,
        )

        timeout_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "timeout"}
        )
        await session.begin()
        timeout_handle = await prepared.prepare(
            ActionId.ACTOR_PROFILE_UPDATE_SELF, timeout_input, scope
        )
        timeout_decision = await prepared.consume(
            timeout_handle,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            timeout_input,
            resource,
        )
        await session.execute(text("update prepared_failure_participant set value=3 where id=1"))
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await asyncio.Event().wait()
        await session.rollback()
        assert (
            await session.scalar(text("select value from prepared_failure_participant where id=1"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(timeout_decision.decision_id)},
            )
            == 0
        )
        await session.rollback()
        await assert_handle_burned_without_reentry(timeout_handle, timeout_input)

        async def cancel_after_consume(phase: str):
            phase_input = PreparedAuthorizationInput(
                idempotency_key=uuid4(), request_value={"case": phase}
            )
            phase_entered = asyncio.Event()
            phase_blocked = asyncio.Event()
            phase_holder = {}

            async def command():
                try:
                    await session.begin()
                    phase_handle = await prepared.prepare(
                        ActionId.ACTOR_PROFILE_UPDATE_SELF, phase_input, scope
                    )
                    phase_decision = await prepared.consume(
                        phase_handle,
                        ActionId.ACTOR_PROFILE_UPDATE_SELF,
                        phase_input,
                        resource,
                    )
                    phase_holder.update(handle=phase_handle, decision=phase_decision)
                    await session.execute(
                        text("update prepared_failure_participant set value=4 where id=1")
                    )
                    phase_entered.set()
                    await phase_blocked.wait()
                    return phase_decision
                except BaseException:
                    await session.rollback()
                    raise

            task = asyncio.create_task(command())
            await asyncio.wait_for(phase_entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (
                await session.scalar(
                    text("select value from prepared_failure_participant where id=1")
                )
                == 0
            )
            assert (
                await session.scalar(
                    text("select count(*) from audit_events where id=:id"),
                    {"id": str(phase_holder["decision"].decision_id)},
                )
                == 0
            )
            assert (
                await session.scalar(
                    text(
                        "select count(*) from authority_idempotency_records "
                        "where idempotency_key=:key"
                    ),
                    {"key": phase_input.idempotency_key},
                )
                == 0
            )
            await session.rollback()
            await assert_handle_burned_without_reentry(
                phase_holder["handle"],
                phase_input,
            )

        await cancel_after_consume("participant_cancel")

        evidence_cancel_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "evidence_cancel"}
        )
        evidence_entered = asyncio.Event()
        evidence_blocked = asyncio.Event()
        evidence_holder = {}

        class PausingEvidence:
            async def add_authority_event(self, _event):
                evidence_holder["decision_id"] = _event.event_id
                evidence_entered.set()
                await evidence_blocked.wait()

        async def cancel_during_evidence():
            try:
                await session.begin()
                handle = await prepared.prepare(
                    ActionId.ACTOR_PROFILE_UPDATE_SELF, evidence_cancel_input, scope
                )
                authorization._audit = PausingEvidence()  # type: ignore[assignment]
                evidence_holder["handle"] = handle
                await prepared.consume(
                    handle,
                    ActionId.ACTOR_PROFILE_UPDATE_SELF,
                    evidence_cancel_input,
                    resource,
                )
            except BaseException:
                await session.rollback()
                raise

        evidence_task = asyncio.create_task(cancel_during_evidence())
        await asyncio.wait_for(evidence_entered.wait(), timeout=5)
        evidence_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await evidence_task
        authorization._audit = original_audit
        assert await session.scalar(text("select 1")) == 1
        await session.rollback()
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(evidence_holder["decision_id"])},
            )
            == 0
        )
        await session.rollback()
        await assert_handle_burned_without_reentry(
            evidence_holder["handle"],
            evidence_cancel_input,
        )

        commit_cancel_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "commit_cancel"}
        )
        commit_entered = asyncio.Event()
        commit_blocked = asyncio.Event()
        original_commit = session.commit
        commit_holder = {}

        async def pausing_commit():
            commit_entered.set()
            await commit_blocked.wait()

        async def cancel_during_commit():
            try:
                await session.begin()
                handle = await prepared.prepare(
                    ActionId.ACTOR_PROFILE_UPDATE_SELF, commit_cancel_input, scope
                )
                decision = await prepared.consume(
                    handle,
                    ActionId.ACTOR_PROFILE_UPDATE_SELF,
                    commit_cancel_input,
                    resource,
                )
                commit_holder.update(handle=handle, decision=decision)
                await session.execute(
                    text("update prepared_failure_participant set value=5 where id=1")
                )
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

        session.commit = pausing_commit  # type: ignore[method-assign]
        commit_task = asyncio.create_task(cancel_during_commit())
        await asyncio.wait_for(commit_entered.wait(), timeout=5)
        commit_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await commit_task
        session.commit = original_commit  # type: ignore[method-assign]
        assert (
            await session.scalar(text("select value from prepared_failure_participant where id=1"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(commit_holder["decision"].decision_id)},
            )
            == 0
        )
        await session.rollback()
        await assert_handle_burned_without_reentry(
            commit_holder["handle"],
            commit_cancel_input,
        )

        async with authorization_factory() as locker:
            await locker.begin()
            await locker.execute(
                text("select id from actor_profiles where id=:id for update"),
                {"id": str(profile_id)},
            )
            async with authorization_factory() as waiter:
                waiter_repository = AdminAuthorizationRepository(waiter)
                waiter_authorization = AuthorizationService(
                    waiter, context, admin_repository=waiter_repository
                )
                waiter_prepared = PreparedAuthorizationService(
                    waiter,
                    context,
                    waiter_authorization,
                    waiter_repository,
                )
                await waiter.begin()
                wait_task = asyncio.create_task(
                    waiter_prepared.prepare(
                        ActionId.ACTOR_PROFILE_UPDATE_SELF,
                        PreparedAuthorizationInput(
                            idempotency_key=uuid4(), request_value={"case": "lock_wait"}
                        ),
                        scope,
                    )
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(wait_task), timeout=0.2)
                wait_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await wait_task
                await waiter.rollback()
                assert await waiter.scalar(text("select 1")) == 1
                await waiter.rollback()
            await locker.rollback()

        await session.execute(text("alter table audit_events disable trigger user"))
        await session.execute(
            text("delete from audit_events where id=:id"),
            {"id": str(success_decision.decision_id)},
        )
        await session.execute(text("alter table audit_events enable trigger user"))
        await session.execute(text("alter table actor_identity_links disable trigger user"))
        await session.execute(text("alter table actor_profiles disable trigger user"))
        await session.execute(
            text("delete from actor_identity_links where id=:id"), {"id": str(link_id)}
        )
        await session.execute(
            text("delete from actor_profiles where id=:id"), {"id": str(profile_id)}
        )
        await session.execute(text("alter table actor_identity_links enable trigger user"))
        await session.execute(text("alter table actor_profiles enable trigger user"))
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation_sql", "mutation_values", "denial_code"),
    [
        (
            "update actor_identity_links set status='revoked', revoked_by=:actor, "
            "revoked_at=:changed_at, revoked_reason='race revoke' where id=:link",
            {},
            AuthorizationDenialCode.IDENTITY_LINK_REVOKED,
        ),
        (
            "update actor_profiles set status='suspended', suspended_by=:actor, "
            "suspended_at=:changed_at, suspension_reason='race suspend' where id=:actor",
            {},
            AuthorizationDenialCode.ACTOR_SUSPENDED,
        ),
        (
            "update actor_profiles set status='deactivated', deactivated_by=:actor, "
            "deactivated_at=:changed_at, deactivation_reason='race deactivate' "
            "where id=:actor",
            {},
            AuthorizationDenialCode.ACTOR_DEACTIVATED,
        ),
    ],
)
async def test_prepared_actor_authority_crossed_mutations_complete_in_both_orders(
    authorization_factory,
    mutation_sql,
    mutation_values,
    denial_code,
) -> None:
    """PostgreSQL proves authority-first waits and mutation-first refreshed denial."""
    profile_id, link_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as seed:
        seed.add_all(
            [
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(profile_id),
                ),
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"prepared-race-{profile_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(profile_id),
                    last_verified_at=now,
                ),
            ]
        )
        await seed.commit()

    context = HumanAuthorizationContext(
        actor_profile_id=profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"display_name": "race"}
    )
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.ACTOR_SELF,
        actor_profile_id=profile_id,
    )
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=profile_id,
        requested_fields=("display_name",),
    )
    values = {
        "actor": str(profile_id),
        "link": str(link_id),
        "changed_at": now,
        **mutation_values,
    }

    async with authorization_factory() as authority_session:
        await authority_session.begin()
        repository = AdminAuthorizationRepository(authority_session)
        authorization = AuthorizationService(
            authority_session, context, admin_repository=repository
        )
        prepared = PreparedAuthorizationService(
            authority_session,
            context,
            authorization,
            repository,
        )
        handle = await prepared.prepare(ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, scope)

        async def mutate_after_prepare():
            async with authorization_factory() as mutation_session:
                await mutation_session.execute(text(mutation_sql), values)
                await mutation_session.commit()

        mutation_task = asyncio.create_task(mutate_after_prepare())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(mutation_task), timeout=0.2)
        decision = await prepared.consume(
            handle, ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, resource
        )
        await authority_session.commit()
        await asyncio.wait_for(mutation_task, timeout=5)

    async with authorization_factory() as verify:
        if denial_code is AuthorizationDenialCode.IDENTITY_LINK_REVOKED:
            assert (
                await verify.scalar(
                    text("select status from actor_identity_links where id=:link"), values
                )
                == "revoked"
            )
        else:
            assert await verify.scalar(
                text("select status from actor_profiles where id=:actor"), values
            ) == denial_code.value.removeprefix("actor_")
        await verify.rollback()

    mutation_first_context = context.model_copy(
        update={"request_id": uuid4(), "correlation_id": uuid4()}
    )
    async with authorization_factory() as denied_session:
        await denied_session.begin()
        denied_repository = AdminAuthorizationRepository(denied_session)
        denied_authorization = AuthorizationService(
            denied_session,
            mutation_first_context,
            admin_repository=denied_repository,
        )
        denied_prepared = PreparedAuthorizationService(
            denied_session,
            mutation_first_context,
            denied_authorization,
            denied_repository,
        )
        with pytest.raises(PreparedAuthorizationUnsupported) as denied:
            await asyncio.wait_for(
                denied_prepared.prepare(ActionId.ACTOR_PROFILE_UPDATE_SELF, caller_input, scope),
                timeout=5,
            )
        assert denied.value.denial_code is denial_code
        await denied_session.rollback()

    async with authorization_factory() as cleanup:
        await cleanup.execute(text("alter table audit_events disable trigger user"))
        await cleanup.execute(
            text("delete from audit_events where id=:id"),
            {"id": str(decision.decision_id)},
        )
        await cleanup.execute(text("alter table audit_events enable trigger user"))
        await cleanup.execute(text("alter table actor_identity_links disable trigger user"))
        await cleanup.execute(text("alter table actor_profiles disable trigger user"))
        await cleanup.execute(text("delete from actor_identity_links where id=:link"), values)
        await cleanup.execute(text("delete from actor_profiles where id=:actor"), values)
        await cleanup.execute(text("alter table actor_identity_links enable trigger user"))
        await cleanup.execute(text("alter table actor_profiles enable trigger user"))
        await cleanup.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation_kind", ["suspend", "deactivate", "link_revoke", "grant_revoke"])
@pytest.mark.parametrize("ordering", ["prepared_first", "mutation_first"])
async def test_prepared_crosses_real_lifecycle_service_transactions(
    authorization_factory,
    mutation_kind,
    ordering,
) -> None:
    """Cross PREP with the existing authorized lifecycle service lock graph."""
    target_profile_id, target_link_id = uuid4(), uuid4()
    mutator_profile_id, mutator_link_id = uuid4(), uuid4()
    target_grant_id, mutator_grant_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as seed:
        await seed.execute(text("alter table admin_role_grants disable trigger user"))
        await seed.execute(text("alter table authority_control disable trigger user"))
        target_profile = ActorProfile(
            id=str(target_profile_id),
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by=str(target_profile_id),
        )
        target_link = ActorIdentityLink(
            id=str(target_link_id),
            actor_profile_id=str(target_profile_id),
            issuer="https://identity.flowresearch.tech",
            subject=f"prepared-real-target-{target_profile_id}",
            subject_kind="human",
            status="active",
            linked_by=str(target_profile_id),
            last_verified_at=now,
        )
        mutator_profile = ActorProfile(
            id=str(mutator_profile_id),
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by=str(mutator_profile_id),
        )
        mutator_link = ActorIdentityLink(
            id=str(mutator_link_id),
            actor_profile_id=str(mutator_profile_id),
            issuer="https://identity.flowresearch.tech",
            subject=f"prepared-real-mutator-{mutator_profile_id}",
            subject_kind="human",
            status="active",
            linked_by=str(mutator_profile_id),
            last_verified_at=now,
        )
        seed.add_all([target_profile, target_link, mutator_profile, mutator_link])
        seed.add(
            AdminRoleGrant(
                id=mutator_grant_id,
                target_actor_profile_id=str(mutator_profile_id),
                role=AdminRole.ACCESS_ADMINISTRATOR.value,
                scope_type=AdminScope.SYSTEM.value,
                status="active",
                version=1,
                granted_by_system_principal="workstream:system:bootstrap",
                grant_reason="prepared race fixture bootstrap",
                granted_at=now,
            )
        )
        await seed.flush()
        seed.add(
            AdminRoleGrant(
                id=target_grant_id,
                target_actor_profile_id=str(target_profile_id),
                role=AdminRole.ACCESS_ADMINISTRATOR.value,
                scope_type=AdminScope.SYSTEM.value,
                status="active",
                version=1,
                granted_by_actor_profile_id=str(mutator_profile_id),
                granted_by_admin_role_grant_id=mutator_grant_id,
                grant_reason="prepared race fixture",
                granted_at=now,
            )
        )
        await seed.flush()
        await seed.execute(
            text(
                "update authority_control set bootstrap_completed=true, version=1, "
                "bootstrap_grant_id=:grant_id, updated_at=clock_timestamp() where id=1"
            ),
            {"grant_id": mutator_grant_id},
        )
        await seed.execute(text("alter table admin_role_grants enable trigger user"))
        await seed.execute(text("alter table authority_control enable trigger user"))
        await seed.commit()

    target_context = HumanAuthorizationContext(
        actor_profile_id=target_profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=target_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    caller_input = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value={"service": "artifact_verifier"}
    )
    prepared_scope = PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
    final_resource = ServiceActorProvisionResourceContext(
        resource_type="service_actor_provisioning",
        resource_id=ServiceIdentity.ARTIFACT_VERIFIER,
    )
    mutation_entered = asyncio.Event()
    release_mutation = asyncio.Event()

    async def run_mutation(*, pause_after_authority: bool) -> None:
        async with authorization_factory() as mutation_session:
            resolved_profile = await mutation_session.get(ActorProfile, str(mutator_profile_id))
            resolved_link = await mutation_session.get(ActorIdentityLink, str(mutator_link_id))
            assert resolved_profile is not None and resolved_link is not None
            resolved = ResolvedActor(resolved_profile, resolved_link)
            mutation_context = HumanAuthorizationContext(
                actor_profile_id=mutator_profile_id,
                actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE,
                identity_link_id=mutator_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
            authorization = AuthorizationService(mutation_session, mutation_context)
            if pause_after_authority:
                repository = authorization._admin
                original_find = repository.find_effective_grant

                async def find_and_pause(*args, **kwargs):
                    grant = await original_find(*args, **kwargs)
                    mutation_entered.set()
                    await release_mutation.wait()
                    return grant

                repository.find_effective_grant = find_and_pause  # type: ignore[method-assign]
            reason = f"prepared real {mutation_kind}"
            if mutation_kind == "grant_revoke":
                await authorization_router.revoke_admin_role_grant(
                    grant_id=target_grant_id,
                    payload=AdminRoleGrantRevokeBody(reason=reason),
                    idempotency_key=uuid4(),
                    resolved=resolved,
                    authorization=authorization,
                    session=mutation_session,
                )
            elif mutation_kind == "link_revoke":
                await authorization_router._mutate_identity_link_lifecycle(
                    identity_link_id=target_link_id,
                    payload=ActorLifecycleBody(reason=reason),
                    idempotency_key=uuid4(),
                    resolved=resolved,
                    authorization=authorization,
                    session=mutation_session,
                    operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
                    action=ActionId.ACTOR_IDENTITY_LINK_REVOKE,
                    transition="revoke",
                )
            else:
                operation = (
                    AuthorityOperation.ACTOR_PROFILE_SUSPEND
                    if mutation_kind == "suspend"
                    else AuthorityOperation.ACTOR_PROFILE_DEACTIVATE
                )
                action = (
                    ActionId.ACTOR_PROFILE_SUSPEND
                    if mutation_kind == "suspend"
                    else ActionId.ACTOR_PROFILE_DEACTIVATE
                )
                await authorization_router._mutate_actor_lifecycle(
                    actor_profile_id=target_profile_id,
                    payload=ActorLifecycleBody(reason=reason),
                    idempotency_key=uuid4(),
                    resolved=resolved,
                    authorization=authorization,
                    session=mutation_session,
                    operation=operation,
                    action=action,
                    transition=mutation_kind,
                )

    async with authorization_factory() as prepared_session:
        await prepared_session.begin()
        repository = AdminAuthorizationRepository(prepared_session)
        authorization = AuthorizationService(
            prepared_session, target_context, admin_repository=repository
        )
        prepared = PreparedAuthorizationService(
            prepared_session,
            target_context,
            authorization,
            repository,
        )
        if ordering == "prepared_first":
            handle = await prepared.prepare(
                ActionId.ACTOR_SERVICE_PROVISION, caller_input, prepared_scope
            )
            mutation_task = asyncio.create_task(run_mutation(pause_after_authority=False))
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(mutation_task), timeout=0.2)
            decision = await prepared.consume(
                handle,
                ActionId.ACTOR_SERVICE_PROVISION,
                caller_input,
                final_resource,
            )
            await prepared_session.commit()
            await asyncio.wait_for(mutation_task, timeout=5)
            assert decision.allowed is True
        else:
            mutation_task = asyncio.create_task(run_mutation(pause_after_authority=True))
            await asyncio.wait_for(mutation_entered.wait(), timeout=5)
            prepare_task = asyncio.create_task(
                prepared.prepare(ActionId.ACTOR_SERVICE_PROVISION, caller_input, prepared_scope)
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(prepare_task), timeout=0.2)
            release_mutation.set()
            await asyncio.wait_for(mutation_task, timeout=5)
            with pytest.raises(PreparedAuthorizationUnsupported) as denied:
                await asyncio.wait_for(prepare_task, timeout=5)
            assert denied.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            await prepared_session.rollback()

    async with authorization_factory() as verify:
        assert (
            await verify.scalar(
                text(
                    "select count(*) from admin_role_grants g "
                    "join actor_profiles p on p.id=g.target_actor_profile_id "
                    "join actor_identity_links l on l.actor_profile_id=p.id "
                    "where g.id in (:target, :mutator) and g.status='active' "
                    "and p.status='active' and l.status='active'"
                ),
                {"target": target_grant_id, "mutator": mutator_grant_id},
            )
            == 1
        )
        if mutation_kind == "grant_revoke":
            assert (
                await verify.scalar(
                    text("select status from admin_role_grants where id=:id"),
                    {"id": target_grant_id},
                )
                == "revoked"
            )
            assert (
                await verify.scalar(
                    text("select version from admin_role_grants where id=:id"),
                    {"id": target_grant_id},
                )
                == 2
            )
        elif mutation_kind == "link_revoke":
            assert (
                await verify.scalar(
                    text("select status from actor_identity_links where id=:id"),
                    {"id": str(target_link_id)},
                )
                == "revoked"
            )
        else:
            assert await verify.scalar(
                text("select status from actor_profiles where id=:id"),
                {"id": str(target_profile_id)},
            ) == ("suspended" if mutation_kind == "suspend" else "deactivated")
        assert (
            await verify.scalar(
                text(
                    "select count(*) from authority_idempotency_records "
                    "where actor_ref=:actor and status='committed'"
                ),
                {"actor": str(mutator_profile_id)},
            )
            == 1
        )
        prepared_allowed = await verify.scalar(
            text(
                "select count(*) from audit_events where action_id=:action "
                "and actor_id=:actor and event_type='SensitiveAuthorizationAllowed'"
            ),
            {
                "action": ActionId.ACTOR_SERVICE_PROVISION.value,
                "actor": str(target_profile_id),
            },
        )
        assert prepared_allowed == (1 if ordering == "prepared_first" else 0)
        await verify.rollback()

    async with authorization_factory() as cleanup:
        actor_ids = (str(target_profile_id), str(mutator_profile_id))
        await cleanup.execute(text("alter table audit_events disable trigger user"))
        await cleanup.execute(
            text(
                "delete from audit_events where actor_id in (:target, :mutator) "
                "or target_actor_ref in (:target, :mutator)"
            ),
            {"target": actor_ids[0], "mutator": actor_ids[1]},
        )
        await cleanup.execute(text("alter table audit_events enable trigger user"))
        await cleanup.execute(
            text("alter table authority_idempotency_records disable trigger user")
        )
        await cleanup.execute(
            text(
                "delete from authority_idempotency_records where actor_ref in (:target, :mutator)"
            ),
            {"target": actor_ids[0], "mutator": actor_ids[1]},
        )
        await cleanup.execute(text("alter table authority_idempotency_records enable trigger user"))
        await cleanup.execute(text("alter table admin_role_grants disable trigger user"))
        await cleanup.execute(text("alter table authority_control disable trigger user"))
        await cleanup.execute(
            text(
                "update authority_control set bootstrap_completed=false, version=0, "
                "bootstrap_grant_id=null, updated_at=clock_timestamp() where id=1"
            )
        )
        await cleanup.execute(
            text("delete from admin_role_grants where id in (:target, :mutator)"),
            {"target": target_grant_id, "mutator": mutator_grant_id},
        )
        await cleanup.execute(text("alter table admin_role_grants enable trigger user"))
        await cleanup.execute(text("alter table authority_control enable trigger user"))
        await cleanup.execute(text("alter table actor_identity_links disable trigger user"))
        await cleanup.execute(text("alter table actor_profiles disable trigger user"))
        await cleanup.execute(
            text("delete from actor_identity_links where id in (:target, :mutator)"),
            {"target": str(target_link_id), "mutator": str(mutator_link_id)},
        )
        await cleanup.execute(
            text("delete from actor_profiles where id in (:target, :mutator)"),
            {"target": actor_ids[0], "mutator": actor_ids[1]},
        )
        await cleanup.execute(text("alter table actor_identity_links enable trigger user"))
        await cleanup.execute(text("alter table actor_profiles enable trigger user"))
        await cleanup.commit()


@pytest.mark.asyncio
async def test_prepared_postgresql_rejects_duplicate_supported_grant_and_reuses_sole_row(
    authorization_factory,
) -> None:
    """Current uniqueness makes two same-role eligible mutation grants impossible."""
    profile_id, link_id = uuid4(), uuid4()
    grant_id, duplicate_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as seed:
        await seed.execute(text("alter table admin_role_grants disable trigger user"))
        seed.add_all(
            [
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(profile_id),
                ),
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"prepared-sole-grant-{profile_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(profile_id),
                    last_verified_at=now,
                ),
                AdminRoleGrant(
                    id=grant_id,
                    target_actor_profile_id=str(profile_id),
                    role=AdminRole.ACCESS_ADMINISTRATOR.value,
                    scope_type=AdminScope.SYSTEM.value,
                    status="active",
                    version=1,
                    granted_by_system_principal="workstream:system:bootstrap",
                    grant_reason="prepared sole grant proof",
                    granted_at=now,
                ),
            ]
        )
        await seed.flush()
        await seed.execute(text("alter table admin_role_grants enable trigger user"))
        await seed.commit()

    async with authorization_factory() as duplicate:
        await duplicate.execute(text("alter table admin_role_grants disable trigger user"))
        duplicate.add(
            AdminRoleGrant(
                id=duplicate_id,
                target_actor_profile_id=str(profile_id),
                role=AdminRole.ACCESS_ADMINISTRATOR.value,
                scope_type=AdminScope.SYSTEM.value,
                status="active",
                version=1,
                granted_by_system_principal="workstream:system:bootstrap",
                grant_reason="must violate active system uniqueness",
                granted_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            await duplicate.commit()
        await duplicate.rollback()

    context = HumanAuthorizationContext(
        actor_profile_id=profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    async with authorization_factory() as session:
        await session.begin()
        repository = AdminAuthorizationRepository(session)
        authorization = AuthorizationService(session, context, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, context, authorization, repository)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"case": "sole_grant"}
        )
        handle = await prepared.prepare(
            ActionId.ACTOR_SERVICE_PROVISION,
            caller_input,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
        )
        decision = await prepared.consume(
            handle,
            ActionId.ACTOR_SERVICE_PROVISION,
            caller_input,
            ServiceActorProvisionResourceContext(
                resource_type="service_actor_provisioning",
                resource_id=ServiceIdentity.ARTIFACT_VERIFIER,
            ),
        )
        assert decision.matched_grant_id == grant_id
        await session.rollback()

    async with authorization_factory() as cleanup:
        await cleanup.execute(text("alter table admin_role_grants disable trigger user"))
        await cleanup.execute(text("delete from admin_role_grants where id=:id"), {"id": grant_id})
        await cleanup.execute(text("alter table admin_role_grants enable trigger user"))
        await cleanup.execute(text("alter table actor_identity_links disable trigger user"))
        await cleanup.execute(text("alter table actor_profiles disable trigger user"))
        await cleanup.execute(
            text("delete from actor_identity_links where id=:id"), {"id": str(link_id)}
        )
        await cleanup.execute(
            text("delete from actor_profiles where id=:id"), {"id": str(profile_id)}
        )
        await cleanup.execute(text("alter table actor_identity_links enable trigger user"))
        await cleanup.execute(text("alter table actor_profiles enable trigger user"))
        await cleanup.commit()


class _AdminPolicyFacts:
    """Configurable canonical facts for focused kernel policy tests."""

    def __init__(self, context: AuthorizationContext) -> None:
        self.context = context
        self.matched: SimpleNamespace | None = SimpleNamespace(id=uuid4())
        self.has_any = False
        self.target_exists = True
        self.project_is_present = True
        self.actor_is_present = True
        self.grant = SimpleNamespace(
            id=uuid4(),
            status="active",
            target_actor_profile_id=str(uuid4()),
        )
        self.request_actor_is_present = True
        self.request_actor_kind = "human"
        self.lifecycle_target_is_present = True
        self.link_lifecycle_target_is_present = True
        self.control_locked = False
        self.find_calls: list[tuple[tuple, dict]] = []

    async def lock_control(self):
        self.control_locked = True
        return SimpleNamespace(id=1)

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        if not self.request_actor_is_present:
            return None
        return (
            SimpleNamespace(id=str(identity_link_id), status="active"),
            SimpleNamespace(
                id=str(actor_profile_id),
                actor_kind=self.request_actor_kind,
                status="active",
            ),
        )

    async def find_effective_grant(self, *args, **kwargs):
        self.find_calls.append((args, kwargs))
        return self.matched

    async def has_effective_permission_any_scope(self, *_args, **_kwargs):
        return self.has_any

    async def lock_eligible_human(self, _actor_profile_id):
        return (object(), object()) if self.target_exists else None

    async def project_exists(self, _project_id, **_kwargs):
        return self.project_is_present

    async def actor_exists(self, _actor_profile_id):
        return self.actor_is_present

    async def get_grant(self, _grant_id, **_kwargs):
        return self.grant

    async def lock_actor_lifecycle_target(self, actor_profile_id):
        if not self.lifecycle_target_is_present:
            return None
        return (
            SimpleNamespace(status="active"),
            SimpleNamespace(id=str(actor_profile_id), status="active"),
            None,
        )

    async def lock_identity_link_lifecycle_target(self, identity_link_id):
        if not self.link_lifecycle_target_is_present:
            return None
        return (
            SimpleNamespace(id=str(identity_link_id), status="active"),
            SimpleNamespace(id=str(uuid4()), actor_kind="human", status="active"),
            None,
        )


def _admin_runtime_service(
    context: AuthorizationContext,
) -> tuple[AuthorizationService, _DecisionEvidence, _AdminPolicyFacts]:
    service, evidence = _runtime_service(context)
    facts = _AdminPolicyFacts(context)
    service._admin = facts  # type: ignore[assignment]
    return service, evidence, facts


async def test_admin_kernel_allows_only_a_matched_registered_grant() -> None:
    context = _runtime_context()
    service, evidence, facts = _admin_runtime_service(context)
    resource = PermissionCatalogueResourceContext(
        resource_type="permission_catalogue",
        resource_id="workstream:permission_catalogue",
    )

    decision = await service.require(ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ, resource)

    assert decision.allowed is True
    assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
    assert decision.matched_grant_id == facts.matched.id
    assert decision.matched_scope_project_id is None
    assert evidence.events[0].matched_grant_id == str(facts.matched.id)

    facts.matched = None
    with pytest.raises(AuthorizationDenied) as denied:
        await service.require(ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ, resource)
    assert denied.value.public_code == "permission_not_granted"


async def test_admin_kernel_denies_locked_human_kind_drift_without_grant_lookup() -> None:
    context = _runtime_context()
    service, evidence, facts = _admin_runtime_service(context)
    facts.request_actor_kind = "service"
    resource = ActorProfileAdminReadResourceContext(
        resource_type="actor_profile",
        resource_id=uuid4(),
        read_kind="profile",
    )

    with pytest.raises(AuthorizationDenied) as denied:
        await service.require(ActionId.ACTOR_PROFILE_READ, resource)

    assert denied.value.decision.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    assert denied.value.decision.revalidated is True
    assert facts.find_calls == []
    assert evidence.events[0].event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED


@pytest.mark.parametrize(
    ("action_id", "resource_type"),
    [
        (ActionId.ACTOR_PROFILE_READ, ActorProfileAdminReadResourceContext),
        (ActionId.ACTOR_IDENTITY_LINK_READ, ActorIdentityLinkAdminReadResourceContext),
    ],
)
async def test_actor_admin_reads_serialize_system_authority_without_control_lock(
    action_id: ActionId,
    resource_type,
) -> None:
    context = _runtime_context()
    service, evidence, facts = _admin_runtime_service(context)
    read_kind = "profile" if action_id is ActionId.ACTOR_PROFILE_READ else "identity_link"
    resource = resource_type(
        resource_type="actor_profile",
        resource_id=uuid4(),
        read_kind=read_kind,
    )

    decision = await service.require(action_id, resource)

    assert decision.allowed is True
    assert decision.revalidated is True
    assert decision.matched_grant_id == facts.matched.id
    assert decision.matched_scope_project_id is None
    assert facts.control_locked is False
    assert facts.find_calls == [
        (
            (context.actor_profile_id, ACTION_BY_ID[action_id].permission_id),
            {
                "scope_project_id": None,
                "system_scope_only": True,
                "for_update": True,
            },
        )
    ]
    assert decision.resource_context_digest == authorization_resource_digest(resource)
    assert evidence.events[0].resource_id == str(resource.resource_id)


@pytest.mark.parametrize(
    ("action_id", "resource"),
    [
        (
            ActionId.ACTOR_PROFILE_READ,
            ActorIdentityLinkAdminReadResourceContext(
                resource_type="actor_profile",
                resource_id=uuid4(),
                read_kind="identity_link",
            ),
        ),
        (
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActorProfileAdminReadResourceContext(
                resource_type="actor_profile",
                resource_id=uuid4(),
                read_kind="profile",
            ),
        ),
    ],
)
async def test_actor_admin_reads_reject_cross_paired_resource_contexts(
    action_id: ActionId,
    resource,
) -> None:
    service, evidence, facts = _admin_runtime_service(_runtime_context())

    with pytest.raises(AuthorizationDenied) as denied:
        await service.require(action_id, resource)

    assert denied.value.public_code == "resource_guard_denied"
    assert facts.find_calls == []
    assert evidence.events[0].after_facts == {"allowed": False}
    assert evidence.events[0].denial_code == "resource_guard_denied"


@pytest.mark.parametrize(
    ("action_id", "transition"),
    [
        (ActionId.ACTOR_PROFILE_SUSPEND, "suspend"),
        (ActionId.ACTOR_PROFILE_REACTIVATE, "reactivate"),
        (ActionId.ACTOR_PROFILE_DEACTIVATE, "deactivate"),
    ],
)
async def test_actor_profile_lifecycle_kernel_locks_control_and_exact_target(
    action_id: ActionId,
    transition: str,
) -> None:
    service, evidence, facts = _admin_runtime_service(_runtime_context())
    resource = ActorProfileLifecycleResourceContext(
        resource_type="actor_profile",
        resource_id=uuid4(),
        transition=transition,
    )

    decision = await service.require(action_id, resource)

    assert decision.allowed is True
    assert decision.revalidated is True
    assert decision.resource_context_digest == authorization_resource_digest(resource)
    assert facts.control_locked is True
    assert evidence.events[0].resource_id == str(resource.resource_id)


async def test_actor_profile_lifecycle_kernel_guards_self_pairing_and_disclosure() -> None:
    context = _runtime_context()
    service, evidence, facts = _admin_runtime_service(context)
    self_resource = ActorProfileLifecycleResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        transition="suspend",
    )
    with pytest.raises(AuthorizationDenied) as self_denial:
        await service.require(ActionId.ACTOR_PROFILE_SUSPEND, self_resource)
    assert self_denial.value.public_code == "resource_guard_denied"

    crossed = self_resource.model_copy(update={"resource_id": uuid4(), "transition": "deactivate"})
    with pytest.raises(AuthorizationDenied) as crossed_denial:
        await service.require(ActionId.ACTOR_PROFILE_SUSPEND, crossed)
    assert crossed_denial.value.public_code == "resource_guard_denied"

    missing = self_resource.model_copy(update={"resource_id": uuid4()})
    facts.lifecycle_target_is_present = False
    with pytest.raises(AuthorizationDenied) as missing_denial:
        await service.require(ActionId.ACTOR_PROFILE_SUSPEND, missing)
    assert missing_denial.value.public_code == "actor_not_found"
    assert [event.denial_code for event in evidence.events] == [
        "resource_guard_denied",
        "resource_guard_denied",
        "actor_not_found",
    ]


@pytest.mark.parametrize(
    ("action_id", "transition"),
    [
        (ActionId.ACTOR_IDENTITY_LINK_REVOKE, "revoke"),
        (ActionId.ACTOR_IDENTITY_LINK_REACTIVATE, "reactivate"),
    ],
)
async def test_identity_link_lifecycle_kernel_locks_control_and_exact_target(
    action_id: ActionId,
    transition: str,
) -> None:
    service, evidence, facts = _admin_runtime_service(_runtime_context())
    resource = ActorIdentityLinkLifecycleResourceContext(
        resource_type="actor_identity_link",
        resource_id=uuid4(),
        transition=transition,
    )

    decision = await service.require(action_id, resource)

    assert decision.allowed is True
    assert decision.revalidated is True
    assert decision.resource_context_digest == authorization_resource_digest(resource)
    assert facts.control_locked is True
    assert evidence.events[0].resource_id == str(resource.resource_id)


async def test_identity_link_lifecycle_kernel_guards_self_pairing_and_disclosure() -> None:
    context = _runtime_context()
    service, evidence, facts = _admin_runtime_service(context)
    self_revoke = ActorIdentityLinkLifecycleResourceContext(
        resource_type="actor_identity_link",
        resource_id=context.identity_link_id,
        transition="revoke",
    )
    with pytest.raises(AuthorizationDenied) as self_denial:
        await service.require(ActionId.ACTOR_IDENTITY_LINK_REVOKE, self_revoke)
    assert self_denial.value.public_code == "resource_guard_denied"

    crossed = self_revoke.model_copy(update={"resource_id": uuid4(), "transition": "reactivate"})
    with pytest.raises(AuthorizationDenied) as crossed_denial:
        await service.require(ActionId.ACTOR_IDENTITY_LINK_REVOKE, crossed)
    assert crossed_denial.value.public_code == "resource_guard_denied"

    missing = self_revoke.model_copy(update={"resource_id": uuid4()})
    facts.link_lifecycle_target_is_present = False
    with pytest.raises(AuthorizationDenied) as missing_denial:
        await service.require(ActionId.ACTOR_IDENTITY_LINK_REVOKE, missing)
    assert missing_denial.value.public_code == "resource_not_found"
    assert [event.denial_code for event in evidence.events] == [
        "resource_guard_denied",
        "resource_guard_denied",
        "resource_not_found",
    ]


def _actor_lifecycle_decision(
    request: ActorProfileSuspendRequest | ActorProfileReactivateRequest,
    *,
    existing: bool,
) -> AuthorizationDecision:
    action = {
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: ActionId.ACTOR_PROFILE_SUSPEND,
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: ActionId.ACTOR_PROFILE_REACTIVATE,
    }[request.operation]
    permission = {
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: PermissionId.ACTOR_PROFILE_SUSPEND,
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: PermissionId.ACTOR_PROFILE_REACTIVATE,
    }[request.operation]
    transition = {
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: "suspend",
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: "reactivate",
    }[request.operation]
    resource = ActorProfileLifecycleResourceContext(
        resource_type="actor_profile",
        resource_id=request.actor_profile_id,
        transition=transition,
        existing_idempotency_record=existing,
    )
    return AuthorizationDecision(
        decision_id=uuid4(),
        action_id=action,
        permission_id=permission,
        allowed=True,
        denial_code=None,
        resource_type="actor_profile",
        resource_id=request.actor_profile_id,
        resource_context_digest=authorization_resource_digest(resource),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=uuid4(),
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


def _identity_link_lifecycle_decision(
    request: ActorIdentityLinkRevokeRequest | ActorIdentityLinkReactivateRequest,
    *,
    existing: bool,
) -> AuthorizationDecision:
    action = {
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: (
            ActionId.ACTOR_IDENTITY_LINK_REACTIVATE
        ),
    }[request.operation]
    permission = {
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: (PermissionId.ACTOR_IDENTITY_LINK_REVOKE),
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: (
            PermissionId.ACTOR_IDENTITY_LINK_REACTIVATE
        ),
    }[request.operation]
    transition = {
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: "revoke",
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: "reactivate",
    }[request.operation]
    resource = ActorIdentityLinkLifecycleResourceContext(
        resource_type="actor_identity_link",
        resource_id=request.identity_link_id,
        transition=transition,
        existing_idempotency_record=existing,
    )
    return AuthorizationDecision(
        decision_id=uuid4(),
        action_id=action,
        permission_id=permission,
        allowed=True,
        denial_code=None,
        resource_type="actor_identity_link",
        resource_id=request.identity_link_id,
        resource_context_digest=authorization_resource_digest(resource),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=uuid4(),
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


async def test_actor_lifecycle_service_rejects_crossed_reason_and_missing_target() -> None:
    target, caller = uuid4(), uuid4()
    reason = "Bounded suspension reason"
    request = ActorProfileSuspendRequest(
        operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        actor_profile_id=target,
        reason_digest=derive_reason_digest(reason),
    )
    decision = _actor_lifecycle_decision(request, existing=False)
    service = ActorLifecycleService(object())  # type: ignore[arg-type]
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(caller),
        operation=request.operation,
        request_digest=DIGEST,
    )

    with pytest.raises(TypeError, match="exact matched authority"):
        await service.complete(
            claim=claim,
            request=request,
            decision=decision.model_copy(update={"revalidated": False}),
            actor_profile_id=caller,
            reason=reason,
        )
    with pytest.raises(TypeError, match="reason digest changed"):
        await service.complete(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=caller,
            reason="Substituted reason",
        )

    class MissingTargetRepository:
        async def lock_actor_lifecycle_target(self, _actor_profile_id):
            return None

    service._repository = MissingTargetRepository()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="target disappeared"):
        await service.complete(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=caller,
            reason=reason,
        )


async def test_actor_lifecycle_service_applies_success_and_guards_conflicts() -> None:
    target, caller = uuid4(), uuid4()
    reason = "Apply exact profile suspension"

    class Session:
        flushed = 0

        async def flush(self):
            self.flushed += 1

    class Repository:
        def __init__(self, profile):
            self.profile = profile

        async def lock_actor_lifecycle_target(self, _actor_profile_id):
            return SimpleNamespace(status="active"), self.profile, None

        async def count_effective_access_administrators(self):
            return 1

    class Mutation:
        completed = None
        mismatch = None

        async def complete(self, **kwargs):
            self.completed = kwargs

        async def record_mismatch_denial(self, **kwargs):
            self.mismatch = kwargs

    class Audit:
        event = None

        async def add_authority_event(self, event):
            self.event = event

    session = Session()
    profile = SimpleNamespace(
        actor_kind="human",
        status="active",
        suspended_by=None,
        suspended_at=None,
        suspension_reason=None,
        reactivated_by=None,
        reactivated_at=None,
        reactivation_reason=None,
        deactivated_by=None,
        deactivated_at=None,
        deactivation_reason=None,
    )
    repository = Repository(profile)
    mutation = Mutation()
    service = ActorLifecycleService(session)  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    service._mutation = mutation  # type: ignore[assignment]
    audit = Audit()
    service._audit = audit  # type: ignore[assignment]
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(caller),
        operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        request_digest=DIGEST,
    )
    request = ActorProfileSuspendRequest(
        operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        actor_profile_id=target,
        reason_digest=derive_reason_digest(reason),
    )
    decision = _actor_lifecycle_decision(request, existing=False)

    response = await service.complete(
        claim=claim,
        request=request,
        decision=decision,
        actor_profile_id=caller,
        reason=reason,
    )
    assert response.resource_id == target
    assert session.flushed == 1
    assert profile.status == "suspended"
    assert profile.suspended_by == str(caller)
    assert profile.suspension_reason == reason
    assert mutation.completed["success"].before_facts == {"status": "active"}
    assert mutation.completed["success"].after_facts == {"status": "suspended"}

    reactivate = ActorProfileReactivateRequest(
        operation=AuthorityOperation.ACTOR_PROFILE_REACTIVATE,
        actor_profile_id=target,
        reason_digest=derive_reason_digest("Reactivate active target"),
    )
    profile.status = "active"
    with pytest.raises(ActorLifecycleConflict) as not_suspended:
        await service.complete(
            claim=claim.model_copy(update={"operation": reactivate.operation}),
            request=reactivate,
            decision=_actor_lifecycle_decision(reactivate, existing=False),
            actor_profile_id=caller,
            reason="Reactivate active target",
        )
    assert not_suspended.value.code == "actor_not_suspended"

    assert (
        await service._conflict(
            request,
            SimpleNamespace(actor_kind="human", status="active"),
            "active",
            True,
        )
        == "last_access_administrator"
    )
    crossed = decision.model_copy(update={"revalidated": False})
    with pytest.raises(TypeError, match="mismatch requires exact authority"):
        await service.record_mismatch(
            actor_profile_id=caller,
            request=request,
            decision=crossed,
        )
    with pytest.raises(TypeError, match="conflict requires exact authority"):
        await service.record_conflict(
            actor_profile_id=caller,
            request=request,
            decision=crossed,
            code="actor_already_suspended",
        )

    await service.record_mismatch(
        actor_profile_id=caller,
        request=request,
        decision=_actor_lifecycle_decision(request, existing=True),
    )
    assert mutation.mismatch["context"].matched_grant_id is None
    await service.record_conflict(
        actor_profile_id=caller,
        request=request,
        decision=decision,
        code="actor_already_suspended",
    )
    assert audit.event.matched_grant_id is None


async def test_identity_link_lifecycle_service_applies_success_and_guards_conflicts() -> None:
    target_link, target_actor, caller = uuid4(), uuid4(), uuid4()
    reason = "Revoke exact identity link"

    class Session:
        flushed = 0

        async def flush(self):
            self.flushed += 1

    class Repository:
        def __init__(self, link, profile):
            self.link = link
            self.profile = profile

        async def lock_identity_link_lifecycle_target(self, _identity_link_id):
            return self.link, self.profile, None

        async def count_effective_access_administrators(self):
            return 1

    class Mutation:
        completed = None
        mismatch = None

        async def complete(self, **kwargs):
            self.completed = kwargs

        async def record_mismatch_denial(self, **kwargs):
            self.mismatch = kwargs

    class Audit:
        event = None

        async def add_authority_event(self, event):
            self.event = event

    session = Session()
    link = SimpleNamespace(
        id=str(target_link),
        status="active",
        revoked_by=None,
        revoked_at=None,
        revoked_reason=None,
        reactivated_by=None,
        reactivated_at=None,
        reactivation_reason=None,
    )
    profile = SimpleNamespace(id=str(target_actor), actor_kind="human", status="active")
    repository = Repository(link, profile)
    mutation = Mutation()
    service = IdentityLinkLifecycleService(session)  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    service._mutation = mutation  # type: ignore[assignment]
    audit = Audit()
    service._audit = audit  # type: ignore[assignment]
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(caller),
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
        request_digest=DIGEST,
    )
    request = ActorIdentityLinkRevokeRequest(
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
        identity_link_id=target_link,
        reason_digest=derive_reason_digest(reason),
    )
    decision = _identity_link_lifecycle_decision(request, existing=False)

    response = await service.complete(
        claim=claim,
        request=request,
        decision=decision,
        actor_profile_id=caller,
        reason=reason,
    )
    assert response == IdentityLinkLifecycleMutationResponse(
        resource_type="actor_identity_link",
        resource_id=target_link,
        version=None,
        http_status=200,
    )
    assert session.flushed == 1
    assert link.status == "revoked"
    assert link.revoked_by == str(caller)
    assert link.revoked_reason == reason
    success = mutation.completed["success"]
    assert success.target_actor_ref == str(target_actor)
    assert success.before_facts == {"status": "active"}
    assert success.after_facts == {"status": "revoked"}

    reactivate_reason = "Reactivate active identity link"
    reactivate = ActorIdentityLinkReactivateRequest(
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE,
        identity_link_id=target_link,
        reason_digest=derive_reason_digest(reactivate_reason),
    )
    link.status = "active"
    with pytest.raises(IdentityLinkLifecycleConflict) as not_revoked:
        await service.complete(
            claim=claim.model_copy(update={"operation": reactivate.operation}),
            request=reactivate,
            decision=_identity_link_lifecycle_decision(reactivate, existing=False),
            actor_profile_id=caller,
            reason=reactivate_reason,
        )
    assert not_revoked.value.code == "identity_link_not_revoked"
    assert not_revoked.value.actor_profile_id == target_actor

    assert (
        await service._conflict(
            request,
            SimpleNamespace(status="active"),
            SimpleNamespace(actor_kind="human", status="active"),
            True,
        )
        == "last_access_administrator"
    )
    crossed = decision.model_copy(update={"revalidated": False})
    with pytest.raises(TypeError, match="mismatch requires exact authority"):
        await service.record_mismatch(
            actor_profile_id=caller,
            request=request,
            decision=crossed,
        )
    with pytest.raises(TypeError, match="conflict requires exact authority"):
        await service.record_conflict(
            actor_profile_id=caller,
            target_actor_profile_id=target_actor,
            request=request,
            decision=crossed,
            code="identity_link_already_revoked",
        )

    await service.record_mismatch(
        actor_profile_id=caller,
        request=request,
        decision=_identity_link_lifecycle_decision(request, existing=True),
    )
    assert mutation.mismatch["context"].matched_grant_id is None
    await service.record_conflict(
        actor_profile_id=caller,
        target_actor_profile_id=target_actor,
        request=request,
        decision=decision,
        code="identity_link_already_revoked",
    )
    assert audit.event.matched_grant_id is None
    assert audit.event.target_actor_ref == str(target_actor)


async def test_admin_kernel_conceals_targets_until_permission_and_scope_match() -> None:
    context = _runtime_context()
    service, _, facts = _admin_runtime_service(context)
    project_id = uuid4()
    resource = AdminRoleGrantCollectionResourceContext(
        resource_type="admin_role_grant_collection",
        resource_id=project_id,
        scope_type=AdminScope.PROJECT,
        scope_project_id=project_id,
    )
    facts.matched = None
    facts.has_any = True
    facts.project_is_present = False

    with pytest.raises(AuthorizationDenied) as wrong_scope:
        await service.require(ActionId.ADMIN_ROLE_GRANT_LIST, resource)
    assert wrong_scope.value.public_code == "scope_not_authorized"

    facts.has_any = False
    with pytest.raises(AuthorizationDenied) as no_permission:
        await service.require(ActionId.ADMIN_ROLE_GRANT_LIST, resource)
    assert no_permission.value.public_code == "permission_not_granted"

    facts.matched = SimpleNamespace(id=uuid4())
    with pytest.raises(AuthorizationDenied) as absent_project:
        await service.require(ActionId.ADMIN_ROLE_GRANT_LIST, resource)
    assert absent_project.value.public_code == "resource_not_found"


async def test_admin_issue_guards_are_central_and_revalidated_under_control_lock() -> None:
    context = _runtime_context()
    service, _, facts = _admin_runtime_service(context)

    self_resource = AdminRoleGrantIssueResourceContext(
        resource_type="admin_role_grant_issue",
        resource_id=context.actor_profile_id,
        role=AdminRole.OPERATOR,
        scope_type=AdminScope.SYSTEM,
    )
    with pytest.raises(AuthorizationDenied) as self_grant:
        await service.require(ActionId.ADMIN_ROLE_GRANT_ISSUE, self_resource)
    assert self_grant.value.public_code == "self_grant_forbidden"
    assert facts.control_locked is True

    facts.request_actor_is_present = False
    target_resource = self_resource.model_copy(update={"resource_id": uuid4()})
    with pytest.raises(AuthorizationDenied) as missing_request_actor:
        await service.require(ActionId.ADMIN_ROLE_GRANT_ISSUE, target_resource)
    assert missing_request_actor.value.public_code == "identity_link_revoked"

    facts.request_actor_is_present = True
    facts.target_exists = False
    with pytest.raises(AuthorizationDenied) as missing_target:
        await service.require(ActionId.ADMIN_ROLE_GRANT_ISSUE, target_resource)
    assert missing_target.value.public_code == "actor_not_found"


async def test_admin_revoke_and_history_guards_fail_closed() -> None:
    context = _runtime_context()
    service, _, facts = _admin_runtime_service(context)
    grant_id = uuid4()
    revoke_resource = AdminRoleGrantResourceContext(
        resource_type="admin_role_grant",
        resource_id=grant_id,
    )
    facts.grant = None
    with pytest.raises(AuthorizationDenied) as missing_grant:
        await service.require(ActionId.ADMIN_ROLE_GRANT_REVOKE, revoke_resource)
    assert missing_grant.value.public_code == "grant_not_found"

    facts.grant = SimpleNamespace(
        id=grant_id,
        status="active",
        target_actor_profile_id=str(context.actor_profile_id),
    )
    with pytest.raises(AuthorizationDenied) as self_revoke:
        await service.require(ActionId.ADMIN_ROLE_GRANT_REVOKE, revoke_resource)
    assert self_revoke.value.public_code == "self_role_revoke_forbidden"

    target_id = uuid4()
    history = ActorAdminRoleGrantHistoryResourceContext(
        resource_type="actor_admin_role_grant_history",
        resource_id=target_id,
        scope_type=AdminScope.SYSTEM,
        scope_project_id=None,
    )
    facts.actor_is_present = False
    with pytest.raises(AuthorizationDenied) as missing_actor:
        await service.require(ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ, history)
    assert missing_actor.value.public_code == "actor_not_found"


@pytest.mark.parametrize(
    ("operation", "decision_change"),
    [
        ("issue", {"action_id": ActionId.ADMIN_ROLE_GRANT_REVOKE}),
        ("issue", {"resource_type": "admin_role_grant"}),
        ("issue", {"resource_id": uuid4()}),
        ("issue", {"permission_id": PermissionId.ADMIN_ROLE_REVOKE}),
        ("issue", {"matched_grant_id": None}),
        ("issue", {"matched_authority_kind": MatchedAuthorityKind.ACTOR_SELF}),
        ("issue", {"matched_scope_project_id": uuid4()}),
        ("issue", {"revalidated": False}),
        ("revoke", {"action_id": ActionId.ADMIN_ROLE_GRANT_ISSUE}),
        ("revoke", {"resource_type": "admin_role_grant_issue"}),
        ("revoke", {"resource_id": uuid4()}),
        ("revoke", {"permission_id": PermissionId.ADMIN_ROLE_GRANT}),
        ("revoke", {"matched_grant_id": None}),
        ("revoke", {"matched_authority_kind": MatchedAuthorityKind.ACTOR_SELF}),
        ("revoke", {"matched_scope_project_id": uuid4()}),
        ("revoke", {"revalidated": False}),
    ],
)
async def test_admin_mutations_reject_decisions_not_bound_to_exact_request(
    operation: str,
    decision_change: dict,
) -> None:
    """Feature mutation cannot consume authority issued for another operation."""
    actor_id, target_id, grant_id, matched_grant_id = uuid4(), uuid4(), uuid4(), uuid4()
    if operation == "issue":
        request = AdminRoleGrantIssueRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
            target_actor_id=target_id,
            role=AdminRole.OPERATOR,
            scope_type=AdminScope.SYSTEM,
            reason_digest=DIGEST,
        )
        action_id = ActionId.ADMIN_ROLE_GRANT_ISSUE
        permission_id = PermissionId.ADMIN_ROLE_GRANT
        resource_type = "admin_role_grant_issue"
        resource_id = target_id
    else:
        request = AdminRoleGrantRevokeRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
            grant_id=grant_id,
            reason_digest=DIGEST,
        )
        action_id = ActionId.ADMIN_ROLE_GRANT_REVOKE
        permission_id = PermissionId.ADMIN_ROLE_REVOKE
        resource_type = "admin_role_grant"
        resource_id = grant_id
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=action_id,
        permission_id=permission_id,
        allowed=True,
        denial_code=None,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_context_digest=authorization_resource_digest(_admin_resource_context(request)),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=matched_grant_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    ).model_copy(update=decision_change)
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=DIGEST,
    )
    service = AdminRoleGrantService(object())  # type: ignore[arg-type]

    if operation == "issue":
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.complete_issue(
                claim=claim,
                request=request,
                decision=decision,
                actor_profile_id=actor_id,
                reason="Bounded reason",
            )
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.record_mismatch(
                actor_profile_id=actor_id,
                request=request,
                decision=decision,
            )
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.record_issue_conflict(
                actor_profile_id=actor_id,
                request=request,
                grant_id=uuid4(),
                decision=decision,
            )
    else:
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.complete_revoke(
                claim=claim,
                request=request,
                decision=decision,
                actor_profile_id=actor_id,
                reason="Bounded reason",
            )
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.record_mismatch(
                actor_profile_id=actor_id,
                request=request,
                decision=decision,
            )
        with pytest.raises(TypeError, match="requires exact matched authority"):
            await service.record_last_admin_denial(
                actor_profile_id=actor_id,
                grant_id=grant_id,
                target_actor_profile_id=target_id,
                decision=decision,
            )


async def test_admin_resource_digest_alone_rejects_substituted_role_and_disposition() -> None:
    """Every admin consumer rejects cross-wiring hidden by equal target IDs."""
    actor_id, target_id, grant_id, matched_grant_id = uuid4(), uuid4(), uuid4(), uuid4()

    class NoWrites:
        def __getattr__(self, name):
            raise AssertionError(f"unexpected write boundary access: {name}")

    issue_request = AdminRoleGrantIssueRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        target_actor_id=target_id,
        role=AdminRole.OPERATOR,
        scope_type=AdminScope.SYSTEM,
        reason_digest=derive_reason_digest("Bound issue reason"),
    )
    substituted_issue_context = AdminRoleGrantIssueResourceContext(
        resource_type="admin_role_grant_issue",
        resource_id=target_id,
        role=AdminRole.ACCESS_ADMINISTRATOR,
        scope_type=AdminScope.SYSTEM,
    )
    issue_digest = authorization_resource_digest(_admin_resource_context(issue_request))
    substituted_issue_digest = authorization_resource_digest(substituted_issue_context)
    assert issue_digest != substituted_issue_digest
    issue_decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_ISSUE,
        permission_id=PermissionId.ADMIN_ROLE_GRANT,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant_issue",
        resource_id=target_id,
        resource_context_digest=substituted_issue_digest,
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=matched_grant_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    issue_claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=issue_request.operation,
        request_digest=DIGEST,
    )
    service = AdminRoleGrantService(object())  # type: ignore[arg-type]
    service._repository = NoWrites()  # type: ignore[assignment]
    service._mutation = NoWrites()  # type: ignore[assignment]
    service._audit = NoWrites()  # type: ignore[assignment]
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.complete_issue(
            claim=issue_claim,
            request=issue_request,
            decision=issue_decision,
            actor_profile_id=actor_id,
            reason="Bound issue reason",
        )
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.record_mismatch(
            actor_profile_id=actor_id,
            request=issue_request,
            decision=issue_decision,
        )
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.record_issue_conflict(
            actor_profile_id=actor_id,
            request=issue_request,
            grant_id=uuid4(),
            decision=issue_decision,
        )

    revoke_request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest("Bound revoke reason"),
    )
    normal_digest = authorization_resource_digest(_admin_resource_context(revoke_request))
    existing_digest = authorization_resource_digest(
        _admin_resource_context(revoke_request, existing_idempotency_record=True)
    )
    assert normal_digest != existing_digest
    revoke_decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_REVOKE,
        permission_id=PermissionId.ADMIN_ROLE_REVOKE,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant",
        resource_id=grant_id,
        resource_context_digest=existing_digest,
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=matched_grant_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    revoke_claim = issue_claim.model_copy(update={"operation": revoke_request.operation})
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.complete_revoke(
            claim=revoke_claim,
            request=revoke_request,
            decision=revoke_decision,
            actor_profile_id=actor_id,
            reason="Bound revoke reason",
        )
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.record_last_admin_denial(
            actor_profile_id=actor_id,
            grant_id=grant_id,
            target_actor_profile_id=target_id,
            decision=revoke_decision,
        )
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.record_mismatch(
            actor_profile_id=actor_id,
            request=revoke_request,
            decision=revoke_decision.model_copy(update={"resource_context_digest": normal_digest}),
        )


async def test_final_access_admin_guard_ignores_ineffective_target_and_is_service_owned() -> None:
    grant_id, target_id = uuid4(), uuid4()
    grant = SimpleNamespace(
        id=grant_id,
        target_actor_profile_id=str(target_id),
        role=AdminRole.ACCESS_ADMINISTRATOR.value,
        scope_type=AdminScope.SYSTEM.value,
        status="active",
    )

    class Facts:
        target_is_effective = False

        async def get_grant(self, _grant_id, **_kwargs):
            return grant

        async def lock_eligible_human(self, _actor_profile_id):
            return (object(), object()) if self.target_is_effective else None

        async def count_effective_access_administrators(self):
            return 1

    service = AdminRoleGrantService(object())  # type: ignore[arg-type]
    facts = Facts()
    service._repository = facts  # type: ignore[assignment]
    original_grant = grant

    async def get_missing_grant(*_args, **_kwargs):
        return None

    facts.get_grant = get_missing_grant  # type: ignore[method-assign]
    assert await service.final_access_administrator_conflict(grant_id) is None

    async def get_revoked_grant(*_args, **_kwargs):
        return SimpleNamespace(**(vars(original_grant) | {"status": "revoked"}))

    facts.get_grant = get_revoked_grant  # type: ignore[method-assign]
    assert await service.final_access_administrator_conflict(grant_id) is None

    async def get_active_grant(*_args, **_kwargs):
        return original_grant

    facts.get_grant = get_active_grant  # type: ignore[method-assign]
    assert await service.final_access_administrator_conflict(grant_id) is None

    facts.target_is_effective = True
    assert await service.final_access_administrator_conflict(grant_id) is grant

    async def force_conflict(_grant_id):
        return grant

    service.final_access_administrator_conflict = force_conflict  # type: ignore[method-assign]
    request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest("Cannot remove final access"),
    )
    actor_id, authorizer_id = uuid4(), uuid4()
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_REVOKE,
        permission_id=PermissionId.ADMIN_ROLE_REVOKE,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant",
        resource_id=grant_id,
        resource_context_digest=authorization_resource_digest(_admin_resource_context(request)),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=authorizer_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=DIGEST,
    )
    with pytest.raises(LastAccessAdministratorConflict) as exc_info:
        await service.complete_revoke(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=actor_id,
            reason="Cannot remove final access",
        )
    assert exc_info.value.grant_id == grant_id
    assert exc_info.value.target_actor_profile_id == target_id


async def test_admin_revoke_stages_complete_state_and_evidence() -> None:
    """A valid revoke mutates history and completes one linked evidence unit."""
    actor_id, target_id, grant_id, authorizer_id = uuid4(), uuid4(), uuid4(), uuid4()
    request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest("Rotation ended"),
    )
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_REVOKE,
        permission_id=PermissionId.ADMIN_ROLE_REVOKE,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant",
        resource_id=grant_id,
        resource_context_digest=authorization_resource_digest(_admin_resource_context(request)),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=authorizer_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=DIGEST,
    )
    grant = SimpleNamespace(
        id=grant_id,
        target_actor_profile_id=str(target_id),
        role=AdminRole.OPERATOR.value,
        scope_type=AdminScope.SYSTEM.value,
        scope_project_id=None,
        status="active",
        version=1,
        revoked_by_actor_profile_id=None,
        revoked_by_admin_role_grant_id=None,
        revoked_reason=None,
        revoked_at=None,
    )

    class Session:
        flush_count = 0
        refresh_count = 0

        async def flush(self):
            self.flush_count += 1

        async def refresh(self, refreshed):
            assert refreshed is grant
            self.refresh_count += 1

    class Repository:
        async def get_grant(self, selected_grant_id, *, for_update=False):
            assert selected_grant_id == grant_id
            assert for_update is True
            return grant

    class Mutation:
        completed = None

        async def complete(self, **kwargs):
            self.completed = kwargs

    session = Session()
    service = AdminRoleGrantService(session)  # type: ignore[arg-type]
    service._repository = Repository()  # type: ignore[assignment]
    mutation = Mutation()
    service._mutation = mutation  # type: ignore[assignment]

    async def no_final_admin_conflict(_grant_id):
        return None

    service.final_access_administrator_conflict = no_final_admin_conflict  # type: ignore[method-assign]

    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.complete_revoke(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=actor_id,
            reason="Cross-wired reason",
        )
    assert grant.status == "active"
    assert session.flush_count == session.refresh_count == 0
    assert mutation.completed is None

    response = await service.complete_revoke(
        claim=claim,
        request=request,
        decision=decision,
        actor_profile_id=actor_id,
        reason="Rotation ended",
    )

    assert response.model_dump(mode="json") == {
        "resource_type": "admin_role_grant",
        "resource_id": str(grant_id),
        "version": 2,
        "http_status": 200,
    }
    assert grant.status == "revoked"
    assert grant.revoked_by_actor_profile_id == str(actor_id)
    assert grant.revoked_by_admin_role_grant_id == authorizer_id
    assert grant.revoked_reason == "Rotation ended"
    assert session.flush_count == session.refresh_count == 1
    assert mutation.completed["success"].event_type is AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED
    assert mutation.completed["success"].target_actor_ref == str(target_id)
    assert mutation.completed["success"].request_id == decision.request_id
    assert mutation.completed["success"].correlation_id == decision.correlation_id
    assert mutation.completed["invalidation"].request_id == decision.request_id
    assert mutation.completed["invalidation"].correlation_id == decision.correlation_id

    class MissingRepository:
        async def get_grant(self, _grant_id, *, for_update=False):
            assert for_update is True
            return None

    service._repository = MissingRepository()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="authorized grant disappeared"):
        await service.complete_revoke(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=actor_id,
            reason="Rotation ended",
        )


async def test_admin_issue_stages_complete_state_and_evidence() -> None:
    """A valid issue returns its bounded reference and linked success evidence."""
    actor_id, target_id, authorizer_id = uuid4(), uuid4(), uuid4()
    request = AdminRoleGrantIssueRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        target_actor_id=target_id,
        role=AdminRole.OPERATOR,
        scope_type=AdminScope.SYSTEM,
        reason_digest=derive_reason_digest("On-call operations coverage"),
    )
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_ISSUE,
        permission_id=PermissionId.ADMIN_ROLE_GRANT,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant_issue",
        resource_id=target_id,
        resource_context_digest=authorization_resource_digest(_admin_resource_context(request)),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=authorizer_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=DIGEST,
    )

    class Repository:
        issued = None

        async def add_grant(self, grant):
            self.issued = grant
            return grant

    class Mutation:
        completed = None

        async def complete(self, **kwargs):
            self.completed = kwargs

    service = AdminRoleGrantService(object())  # type: ignore[arg-type]
    repository = Repository()
    mutation = Mutation()
    service._repository = repository  # type: ignore[assignment]
    service._mutation = mutation  # type: ignore[assignment]
    with pytest.raises(TypeError, match="requires exact matched authority"):
        await service.complete_issue(
            claim=claim,
            request=request,
            decision=decision,
            actor_profile_id=actor_id,
            reason="Cross-wired reason",
        )
    assert repository.issued is None
    assert mutation.completed is None

    response = await service.complete_issue(
        claim=claim,
        request=request,
        decision=decision,
        actor_profile_id=actor_id,
        reason="On-call operations coverage",
    )

    assert response.resource_id == repository.issued.id
    assert response.version == 1
    assert response.http_status == 201
    assert repository.issued.target_actor_profile_id == str(target_id)
    assert repository.issued.granted_by_admin_role_grant_id == authorizer_id
    assert mutation.completed["success"].event_type is AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED
    assert mutation.completed["success"].request_id == decision.request_id
    assert mutation.completed["success"].correlation_id == decision.correlation_id
    assert mutation.completed["invalidation"].request_id == decision.request_id
    assert mutation.completed["invalidation"].correlation_id == decision.correlation_id


async def test_admin_grant_pagination_and_bootstrap_corruption_fail_closed() -> None:
    """Pagination is stable, while malformed cursors/control rows fail closed."""
    now = datetime.now(UTC)

    def grant(index: int):
        return SimpleNamespace(
            id=uuid4(),
            target_actor_profile_id=str(uuid4()),
            role=AdminRole.OPERATOR.value,
            scope_type=AdminScope.SYSTEM.value,
            scope_project_id=None,
            status="active",
            version=1,
            granted_by_system_principal="workstream:system:bootstrap",
            granted_by_actor_profile_id=None,
            granted_by_admin_role_grant_id=None,
            grant_reason=f"grant-{index}",
            granted_at=now,
            revoked_by_actor_profile_id=None,
            revoked_by_admin_role_grant_id=None,
            revoked_reason=None,
            revoked_at=None,
        )

    rows = [grant(1), grant(2)]

    class Repository:
        decoded_cursor = None

        async def list_grants(self, **kwargs):
            self.decoded_cursor = kwargs["cursor"]
            return rows, 2

        async def get_eligible_human(self, _actor_id):
            return None

        async def lock_control(self):
            return self.control

        async def lock_eligible_human(self, _actor_id):
            return None

    class Session:
        control = None

        async def get(self, _model, _key):
            return self.control

    session = Session()
    repository = Repository()
    service = AdminRoleGrantService(session)  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    page = await service.list_page(
        scope_type=AdminScope.SYSTEM,
        scope_project_id=None,
        target_actor_profile_id=None,
        status="active",
        limit=1,
        cursor=None,
    )
    assert len(page.items) == 1
    assert page.total == 2
    assert page.next_cursor is not None
    await service.list_page(
        scope_type=AdminScope.SYSTEM,
        scope_project_id=None,
        target_actor_profile_id=None,
        status="active",
        limit=1,
        cursor=page.next_cursor,
    )
    assert repository.decoded_cursor == (now, rows[0].id)

    malformed_payloads = [
        {"unexpected": "mapping"},
        [now.isoformat(), "not-a-uuid"],
        [now.replace(tzinfo=None).isoformat(), str(uuid4())],
    ]
    for payload in malformed_payloads:
        cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        with pytest.raises(ValueError, match="invalid cursor"):
            await service.list_page(
                scope_type=AdminScope.SYSTEM,
                scope_project_id=None,
                target_actor_profile_id=None,
                status="active",
                limit=1,
                cursor=cursor,
            )

    actor_id, completed_grant_id = uuid4(), uuid4()
    with pytest.raises(RuntimeError, match="authority control is missing"):
        await service.bootstrap_eligible(actor_id)
    session.control = SimpleNamespace(bootstrap_completed=True, bootstrap_grant_id=None)
    with pytest.raises(RuntimeError, match="missing its grant"):
        await service.bootstrap_eligible(actor_id)
    session.control.bootstrap_grant_id = completed_grant_id
    with pytest.raises(BootstrapAlreadyCompleted) as completed:
        await service.bootstrap_eligible(actor_id)
    assert completed.value.grant_id == completed_grant_id

    repository.control = SimpleNamespace(bootstrap_completed=True, bootstrap_grant_id=None)
    with pytest.raises(RuntimeError, match="missing its grant"):
        await service.bootstrap(actor_id)
    repository.control = SimpleNamespace(bootstrap_completed=False, bootstrap_grant_id=None)
    with pytest.raises(BootstrapTargetIneligible):
        await service.bootstrap(actor_id)


async def test_post_allow_admin_denials_preserve_matched_grant_provenance() -> None:
    actor_id, target_id, matched_grant_id = uuid4(), uuid4(), uuid4()
    request = AdminRoleGrantIssueRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        target_actor_id=target_id,
        role=AdminRole.OPERATOR,
        scope_type=AdminScope.SYSTEM,
        reason_digest=DIGEST,
    )
    decision = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ADMIN_ROLE_GRANT_ISSUE,
        permission_id=PermissionId.ADMIN_ROLE_GRANT,
        allowed=True,
        denial_code=None,
        resource_type="admin_role_grant_issue",
        resource_id=target_id,
        resource_context_digest=authorization_resource_digest(_admin_resource_context(request)),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=matched_grant_id,
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )

    class EvidenceRepository:
        def __init__(self) -> None:
            self.events = []

        async def _add_validated_authority_event(self, event):
            self.events.append(event)
            return event

    evidence = EvidenceRepository()
    audit = AuditService(object())  # type: ignore[arg-type]
    audit._repository = evidence  # type: ignore[assignment]
    service = AdminRoleGrantService(object())  # type: ignore[arg-type]
    service._mutation._audit = audit
    await service.record_mismatch(
        actor_profile_id=actor_id,
        request=request,
        decision=decision,
    )
    service._audit = audit
    await service.record_issue_conflict(
        actor_profile_id=actor_id,
        request=request,
        grant_id=uuid4(),
        decision=decision,
    )
    revoke_grant_id = uuid4()
    revoke_request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=revoke_grant_id,
        reason_digest=DIGEST,
    )
    revoke_decision = decision.model_copy(
        update={
            "action_id": ActionId.ADMIN_ROLE_GRANT_REVOKE,
            "permission_id": PermissionId.ADMIN_ROLE_REVOKE,
            "resource_type": "admin_role_grant",
            "resource_id": revoke_grant_id,
            "resource_context_digest": authorization_resource_digest(
                _admin_resource_context(revoke_request)
            ),
        }
    )
    await service.record_last_admin_denial(
        actor_profile_id=actor_id,
        grant_id=revoke_grant_id,
        target_actor_profile_id=target_id,
        decision=revoke_decision,
    )

    assert [event.matched_grant_id for event in evidence.events] == [
        str(matched_grant_id),
        str(matched_grant_id),
        str(matched_grant_id),
    ]
    assert evidence.events[0].action_id == ActionId.ADMIN_ROLE_GRANT_ISSUE.value
    assert evidence.events[0].permission_id == PermissionId.ADMIN_ROLE_GRANT.value
    assert {(event.request_id, event.correlation_id) for event in evidence.events} == {
        (str(decision.request_id), str(decision.correlation_id))
    }


async def test_authorization_dependency_rolls_back_a_forgotten_route_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForgottenCommitSession:
        def __init__(self) -> None:
            self.rollback_count = 0

        def in_transaction(self) -> bool:
            return True

        async def rollback(self) -> None:
            self.rollback_count += 1

    actor_id, link_id = uuid4(), uuid4()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id), actor_kind="human", status="active"),
        identity_link=SimpleNamespace(id=str(link_id), status="active"),
    )
    session = ForgottenCommitSession()
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, session)  # type: ignore[arg-type]
    service = await anext(dependency)
    evidence = _DecisionEvidence()
    service._audit = evidence  # type: ignore[assignment]

    async def retain_resolved_actor(_service, current):
        return current

    monkeypatch.setattr(
        ActorService,
        "lock_actor_self_for_authorization",
        retain_resolved_actor,
    )

    await service.require(
        ActionId.ACTOR_PROFILE_READ_SELF,
        ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=actor_id,
            requested_fields=(),
        ),
    )
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    assert len(evidence.events) == 1
    assert session.rollback_count == 1


async def test_prepared_dependency_closes_handles_without_committing() -> None:
    class Session:
        commit_count = 0
        rollback_count = 0

        async def commit(self):
            self.commit_count += 1

        async def rollback(self):
            self.rollback_count += 1

        def in_transaction(self):
            return False

    actor_id, link_id = uuid4(), uuid4()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id), actor_kind="human", status="active"),
        identity_link=SimpleNamespace(id=str(link_id), status="active"),
    )
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    session = Session()
    dependency = get_prepared_authorization_service(
        request,
        resolved,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    service = await anext(dependency)
    assert service._closed is False
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert service._closed is True
    assert session.commit_count == 0

    denial_session = Session()
    denial_dependency = get_prepared_authorization_service(
        request,
        resolved,  # type: ignore[arg-type]
        denial_session,  # type: ignore[arg-type]
    )
    await anext(denial_dependency)
    denied = AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ACTOR_PROFILE_UPDATE_SELF,
        permission_id=PermissionId.ACTOR_PROFILE_UPDATE_SELF,
        allowed=False,
        denial_code=AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        resource_type="actor_profile",
        resource_id=actor_id,
        resource_context_digest=authorization_resource_digest(
            ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=actor_id,
                requested_fields=("display_name",),
            )
        ),
        matched_authority_kind=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    with pytest.raises(StructuredHTTPException):
        await denial_dependency.athrow(  # type: ignore[attr-defined]
            AuthorizationDenied(denied)
        )
    assert denial_session.rollback_count == 1
    assert denial_session.commit_count == 0


async def test_authorization_dependency_admits_service_without_human_rate_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = SimpleNamespace(subject_kind="service")
    admitted = SimpleNamespace(profile=object(), identity_link=object())
    calls: list[object] = []

    async def resolve_service(_self, current):
        calls.append(current)
        return admitted

    async def forbidden_human_lookup(*_args, **_kwargs):
        raise AssertionError("service admission entered the human path")

    monkeypatch.setattr(ActorService, "resolve_service_for_authorization", resolve_service)
    monkeypatch.setattr(
        ActorService,
        "find_actor_for_authorization",
        forbidden_human_lookup,
    )
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    result = SimpleNamespace(token=token)

    resolved = await get_authorization_actor(
        request,
        result,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )

    assert resolved is admitted
    assert calls == [token]


@pytest.mark.parametrize(
    ("profile_status", "link_status"),
    [("suspended", "active"), ("deactivated", "active"), ("active", "revoked")],
)
async def test_inactive_service_dependency_stages_no_observation(
    monkeypatch: pytest.MonkeyPatch,
    profile_status: str,
    link_status: str,
) -> None:
    class Session:
        async def rollback(self):
            return None

        def in_transaction(self):
            return True

    async def forbidden_touch(*_args, **_kwargs):
        raise AssertionError("inactive service staged an observation")

    monkeypatch.setattr(ActorService, "touch_after_authorization", forbidden_touch)
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(uuid4()),
            actor_kind="service",
            status=profile_status,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        ),
        identity_link=SimpleNamespace(id=str(uuid4()), status=link_status),
    )
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, Session())  # type: ignore[arg-type]

    await anext(dependency)
    await dependency.aclose()


async def test_service_denial_rolls_back_observations_before_clean_restage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        rollback_count = 0
        commit_count = 0

        async def rollback(self):
            self.rollback_count += 1

        async def commit(self):
            self.commit_count += 1

        def in_transaction(self):
            return True

    session = Session()
    actor_id, link_id = uuid4(), uuid4()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(actor_id),
            actor_kind="service",
            status="active",
            service_identity=ServiceIdentity.ARTIFACT_SCHEDULER.value,
        ),
        identity_link=SimpleNamespace(id=str(link_id), status="active"),
    )
    observations: list[str] = []

    async def stage_observation(_self, _resolved):
        observations.append("staged")
        return _resolved

    monkeypatch.setattr(ActorService, "touch_after_authorization", stage_observation)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, session)  # type: ignore[arg-type]
    service = await anext(dependency)

    class Evidence:
        rollback_counts: list[int] = []

        async def add_authority_event(self, _event):
            self.rollback_counts.append(session.rollback_count)

    evidence = Evidence()
    service._audit = evidence  # type: ignore[assignment]
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.ARTIFACT_VERIFICATION_EXECUTE, resource)
    with pytest.raises(StructuredHTTPException) as public:
        await dependency.athrow(exc_info.value)  # type: ignore[attr-defined]

    assert public.value.error_code == "permission_not_granted"
    assert observations == ["staged"]
    assert evidence.rollback_counts == [0, 1]
    assert session.rollback_count == 1
    assert session.commit_count == 1


async def test_service_dependency_cancellation_rolls_back_staged_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        rollback_count = 0

        async def rollback(self):
            self.rollback_count += 1

        def in_transaction(self):
            return True

    session = Session()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(uuid4()),
            actor_kind="service",
            status="active",
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        ),
        identity_link=SimpleNamespace(id=str(uuid4()), status="active"),
    )
    observations: list[str] = []

    async def stage_observation(_self, _resolved):
        observations.append("staged")
        return _resolved

    monkeypatch.setattr(ActorService, "touch_after_authorization", stage_observation)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, session)  # type: ignore[arg-type]
    await anext(dependency)

    with pytest.raises(asyncio.CancelledError):
        await dependency.athrow(  # type: ignore[attr-defined]
            asyncio.CancelledError()
        )

    assert observations == ["staged"]
    assert session.rollback_count == 1


async def test_service_observation_persistence_failure_is_retryable_and_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_subject = "private-service-subject"

    class Session:
        rollback_count = 0

        async def rollback(self):
            self.rollback_count += 1

    session = Session()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(uuid4()),
            actor_kind="service",
            status="active",
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        ),
        identity_link=SimpleNamespace(id=str(uuid4()), status="active"),
    )

    async def fail_observation(_self, _resolved):
        raise SQLAlchemyError(private_subject)

    monkeypatch.setattr(ActorService, "touch_after_authorization", fail_observation)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, session)  # type: ignore[arg-type]

    with pytest.raises(StructuredHTTPException) as exc_info:
        await anext(dependency)

    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "service_unavailable"
    assert private_subject not in str(exc_info.value)
    assert session.rollback_count == 1


def test_authorization_runtime_contracts_are_strict_and_two_argument() -> None:
    context = _runtime_context()
    public_methods = {
        name
        for name, member in inspect.getmembers(AuthorizationService, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {"require", "restage_denial"}
    assert tuple(inspect.signature(AuthorizationService.require).parameters) == (
        "self",
        "action_id",
        "resource_context",
    )
    for method in (
        AdminRoleGrantService.complete_issue,
        AdminRoleGrantService.complete_revoke,
        AdminRoleGrantService.record_mismatch,
        AdminRoleGrantService.record_issue_conflict,
        AdminRoleGrantService.record_last_admin_denial,
    ):
        assert "request_id" not in inspect.signature(method).parameters
        assert "correlation_id" not in inspect.signature(method).parameters
    with pytest.raises(ValidationError):
        HumanAuthorizationContext(
            **context.model_dump(),
            roles=("admin",),
        )
    with pytest.raises(ValidationError):
        HumanAuthorizationContext(
            **context.model_dump(),
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
        )
    with pytest.raises(ValidationError):
        ServiceAuthorizationContext(
            **{**context.model_dump(), "actor_kind": ActorKind.SERVICE},
        )
    with pytest.raises(ValidationError):
        ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=context.actor_profile_id,
            requested_fields=("display_name", "display_name"),
        )
    with pytest.raises(ValidationError):
        ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=str(context.actor_profile_id),
            requested_fields=(),
        )


def test_feature_authorization_import_boundary_rejects_persistence_and_private_helpers() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    forbidden: list[tuple[str, str]] = []
    for relative in ("modules/actors/service.py", "api/routes/auth.py"):
        tree = ast.parse((app_root / relative).read_text(), filename=relative)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module in {
                "app.modules.authorization.models",
                "app.modules.authorization.repository",
            } or node.module.startswith("app.modules.authorization._"):
                forbidden.append((relative, node.module))
    assert forbidden == []


async def test_authorization_kernel_allows_only_exact_actor_self_actions() -> None:
    context = _runtime_context()
    service, evidence = _runtime_service(context)
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=(),
    )

    decision = await service.require(ActionId.ACTOR_PROFILE_READ_SELF, resource)

    assert decision.allowed is True
    assert decision.action_id is ActionId.ACTOR_PROFILE_READ_SELF
    assert decision.permission_id is PermissionId.ACTOR_PROFILE_READ_SELF
    assert decision.revalidated is True
    assert len(evidence.events) == 1
    assert evidence.events[0].action_id is ActionId.ACTOR_PROFILE_READ_SELF
    assert evidence.events[0].after_facts == {"allowed": True}


@pytest.mark.parametrize(
    ("action", "resource", "expected"),
    [
        (
            ActionId.REVIEW_QUEUE_READ,
            SystemResourceContext(resource_type="system", resource_id="workstream:system"),
            AuthorizationDenialCode.ACTION_UNAVAILABLE,
        ),
        (
            ActionId.ACTOR_PROFILE_READ_SELF,
            SystemResourceContext(resource_type="system", resource_id="workstream:system"),
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        ),
    ],
)
async def test_authorization_kernel_denies_planned_and_system_actions(
    action,
    resource,
    expected: AuthorizationDenialCode,
) -> None:
    service, evidence = _runtime_service(_runtime_context())

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    assert exc_info.value.decision.denial_code is expected
    assert exc_info.value.public_code in {"permission_not_granted", "resource_guard_denied"}
    assert evidence.events[0].event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED


async def test_fixed_service_kernel_selects_exact_action_before_availability() -> None:
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")
    for identity, own_actions in SERVICE_ACTIONS_BY_IDENTITY.items():
        context = ServiceAuthorizationContext(
            actor_profile_id=uuid4(),
            actor_kind=ActorKind.SERVICE,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=uuid4(),
            identity_link_status=IdentityLinkStatus.ACTIVE,
            service_identity=identity,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        service, _ = _runtime_service(context)
        for action in set().union(*SERVICE_ACTIONS_BY_IDENTITY.values()):
            with pytest.raises(AuthorizationDenied) as exc_info:
                await service.require(action, resource)
            expected = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            if action in own_actions:
                expected = (
                    AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                    if ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
                    else AuthorizationDenialCode.ACTION_UNAVAILABLE
                )
            assert exc_info.value.decision.denial_code is expected


async def test_fixed_service_kernel_never_enters_human_grant_evaluation() -> None:
    context = _runtime_context(actor_kind=ActorKind.SERVICE)
    service, _ = _runtime_service(context)

    class HumanFacts:
        async def find_effective_grant(self, *_args, **_kwargs):
            raise AssertionError("service context entered human grant evaluation")

    service._admin = HumanFacts()  # type: ignore[assignment]
    resource = PermissionCatalogueResourceContext(
        resource_type="permission_catalogue",
        resource_id="workstream:permission_catalogue",
    )
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ, resource)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED


async def test_fixed_service_active_candidate_uses_one_revalidation_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _runtime_context(actor_kind=ActorKind.SERVICE)
    calls: list[tuple[ServiceIdentity, ActionId]] = []

    async def revalidate(current: ServiceAuthorizationContext, action: ActionId):
        calls.append((current.service_identity, action))
        return current

    service, _ = _runtime_service(context, revalidate_service=revalidate)
    action = ActionId.ARTIFACT_VERIFICATION_EXECUTE
    definition = ACTION_BY_ID[action]
    monkeypatch.setattr(
        authorization_kernel,
        "ACTION_BY_ID",
        {
            **ACTION_BY_ID,
            action: replace(definition, availability=ActionAvailability.ACTIVE),
        },
    )
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert exc_info.value.decision.revalidated is True
    assert calls == [(ServiceIdentity.ARTIFACT_VERIFIER, action)]


async def test_fixed_service_active_artifact_action_requires_prepared_consumption() -> None:
    context = _runtime_context(actor_kind=ActorKind.SERVICE)

    async def revalidate(current: ServiceAuthorizationContext, _action: ActionId):
        return current

    service, evidence = _runtime_service(context, revalidate_service=revalidate)
    resource = ArtifactVerificationJobResourceContext(
        resource_type="artifact_verification_job",
        resource_id=uuid4(),
        replica_id=uuid4(),
        namespace_fingerprint="sha256:" + "1" * 64,
        provider_object_ref="provider/object",
        sha256="sha256:" + "2" * 64,
        byte_count=1,
        executor_id=uuid4(),
        execution_generation=1,
    )

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.ARTIFACT_VERIFICATION_EXECUTE, resource)

    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert exc_info.value.decision.allowed is False
    assert evidence.events[-1].after_facts["allowed"] is False
    assert evidence.events[-1].after_facts["resource_context_digest"] == (
        authorization_resource_digest(resource)
    )


@pytest.mark.parametrize(
    ("actor_status", "link_status", "expected"),
    [
        (
            ActorStatus.ACTIVE,
            IdentityLinkStatus.REVOKED,
            AuthorizationDenialCode.IDENTITY_LINK_REVOKED,
        ),
        (ActorStatus.SUSPENDED, IdentityLinkStatus.ACTIVE, AuthorizationDenialCode.ACTOR_SUSPENDED),
        (
            ActorStatus.DEACTIVATED,
            IdentityLinkStatus.ACTIVE,
            AuthorizationDenialCode.ACTOR_DEACTIVATED,
        ),
    ],
)
async def test_fixed_service_lifecycle_denies_before_matrix_evaluation(
    actor_status: ActorStatus,
    link_status: IdentityLinkStatus,
    expected: AuthorizationDenialCode,
) -> None:
    context = _runtime_context(
        actor_kind=ActorKind.SERVICE,
        actor_status=actor_status,
        link_status=link_status,
    )
    service, _ = _runtime_service(context)
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.ARTIFACT_VERIFICATION_EXECUTE, resource)

    assert exc_info.value.decision.denial_code is expected


@pytest.mark.parametrize(
    ("profile_status", "link_status", "service_identity", "expected"),
    [
        (
            "suspended",
            "active",
            ServiceIdentity.ARTIFACT_VERIFIER.value,
            AuthorizationDenialCode.ACTOR_SUSPENDED,
        ),
        (
            "deactivated",
            "active",
            ServiceIdentity.ARTIFACT_VERIFIER.value,
            AuthorizationDenialCode.ACTOR_DEACTIVATED,
        ),
        (
            "active",
            "revoked",
            ServiceIdentity.ARTIFACT_VERIFIER.value,
            AuthorizationDenialCode.IDENTITY_LINK_REVOKED,
        ),
        (
            "active",
            "active",
            ServiceIdentity.ARTIFACT_SCHEDULER.value,
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
        (
            "active",
            "active",
            "malformed-service-identity",
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
    ],
)
async def test_fixed_service_real_revalidation_rejects_locked_drift(
    monkeypatch: pytest.MonkeyPatch,
    profile_status: str,
    link_status: str,
    service_identity: str,
    expected: AuthorizationDenialCode,
) -> None:
    class Session:
        async def rollback(self):
            return None

        def in_transaction(self):
            return True

    actor_id, link_id = uuid4(), uuid4()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(actor_id),
            actor_kind="service",
            status="active",
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        ),
        identity_link=SimpleNamespace(id=str(link_id), status="active"),
    )
    locked = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(actor_id),
            actor_kind="service",
            status=profile_status,
            service_identity=service_identity,
        ),
        identity_link=SimpleNamespace(id=str(link_id), status=link_status),
    )

    async def no_observation(_self, current):
        return current

    async def lock_drifted(_self, _resolved):
        return locked

    monkeypatch.setattr(ActorService, "touch_after_authorization", no_observation)
    monkeypatch.setattr(ActorService, "lock_actor_for_authorization", lock_drifted)

    action = ActionId.ARTIFACT_VERIFICATION_EXECUTE
    monkeypatch.setattr(
        authorization_kernel,
        "ACTION_BY_ID",
        {
            **ACTION_BY_ID,
            action: replace(ACTION_BY_ID[action], availability=ActionAvailability.ACTIVE),
        },
    )
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    dependency = get_authorization_service(request, resolved, Session())  # type: ignore[arg-type]
    service = await anext(dependency)

    class Evidence:
        async def add_authority_event(self, _event):
            return None

    service._audit = Evidence()  # type: ignore[assignment]
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    assert exc_info.value.decision.denial_code is expected
    assert exc_info.value.decision.revalidated is True
    await dependency.aclose()


@pytest.mark.parametrize("drift", ["matrix", "availability"])
async def test_fixed_service_revalidation_rejects_matrix_or_availability_drift(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    context = _runtime_context(actor_kind=ActorKind.SERVICE)
    action = ActionId.ARTIFACT_VERIFICATION_EXECUTE
    active_actions = {
        **ACTION_BY_ID,
        action: replace(ACTION_BY_ID[action], availability=ActionAvailability.ACTIVE),
    }
    monkeypatch.setattr(authorization_kernel, "ACTION_BY_ID", active_actions)

    async def revalidate(current: ServiceAuthorizationContext, _action: ActionId):
        if drift == "matrix":
            monkeypatch.setattr(
                authorization_kernel,
                "SERVICE_ACTIONS_BY_IDENTITY",
                {**SERVICE_ACTIONS_BY_IDENTITY, current.service_identity: frozenset()},
            )
        else:
            monkeypatch.setattr(
                authorization_kernel,
                "ACTION_BY_ID",
                {
                    **active_actions,
                    action: replace(
                        active_actions[action], availability=ActionAvailability.PLANNED
                    ),
                },
            )
        return current

    service, _ = _runtime_service(context, revalidate_service=revalidate)
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    assert exc_info.value.decision.revalidated is True


async def test_authorization_kernel_denies_active_action_without_implemented_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _runtime_context()
    service, evidence = _runtime_service(context)
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=(),
    )
    active_unhandled = ActionDefinition(
        action_id=ActionId.REVIEW_QUEUE_READ,
        permission_id=PermissionId.REVIEW_QUEUE_READ,
        owner=ActionOwner.AUTH_REV_05,
        availability=ActionAvailability.ACTIVE,
    )
    monkeypatch.setattr(
        authorization_kernel,
        "ACTION_BY_ID",
        {**ACTION_BY_ID, active_unhandled.action_id: active_unhandled},
    )

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(active_unhandled.action_id, resource)

    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE
    assert evidence.events[0].event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED


@pytest.mark.parametrize(
    ("action_id", "expected_metadata"),
    {
        action_id: metadata
        for action_id, metadata in {
            **ART_CUSTODY_EXPECTATIONS,
            **REV_CUSTODY_EXPECTATIONS,
        }.items()
        if metadata[2] == "planned"
    }.items(),
)
async def test_custody_actions_remain_unavailable_without_runtime_dispatch(
    action_id: str,
    expected_metadata: tuple[str, str, str],
) -> None:
    expected_permission, _owner, expected_availability = expected_metadata
    action = ActionId(action_id)
    context = _runtime_context()

    async def unexpected_revalidation(*_args, **_kwargs):
        raise AssertionError("planned custody action reached runtime revalidation")

    class UnexpectedAuthorizationDependency:
        def __getattr__(self, name: str):
            async def unexpected(*_args, **_kwargs):
                raise AssertionError(f"planned custody action reached {name}")

            return unexpected

    service, evidence = _runtime_service(context, revalidate=unexpected_revalidation)
    service._admin = UnexpectedAuthorizationDependency()  # type: ignore[assignment]
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    decision = exc_info.value.decision
    assert decision.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE
    assert decision.action_id is action
    assert decision.permission_id is PermissionId(expected_permission)
    assert ACTION_BY_ID[action].availability.value == expected_availability
    assert decision.revalidated is False
    assert len(evidence.events) == 1
    assert evidence.events[0].event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED
    assert evidence.events[0].action_id == action_id
    assert evidence.events[0].permission_id == expected_permission


async def test_unknown_action_denies_without_fabricated_evidence() -> None:
    context = _runtime_context()
    service, evidence = _runtime_service(context)
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=(),
    )

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require("unknown.action", resource)  # type: ignore[arg-type]

    assert exc_info.value.decision.action_id is None
    assert exc_info.value.decision.permission_id is None
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.UNKNOWN_ACTION
    assert exc_info.value.public_code == "permission_not_granted"
    assert evidence.events == []


async def test_denial_is_restaged_with_the_same_bounded_identity() -> None:
    context = _runtime_context()
    service, evidence = _runtime_service(context)
    resource = SystemResourceContext(resource_type="system", resource_id="workstream:system")
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(ActionId.REVIEW_QUEUE_READ, resource)
    original = evidence.events.pop()

    await service.restage_denial(exc_info.value.decision)

    assert len(evidence.events) == 1
    assert evidence.events[0].event_id == original.event_id
    assert evidence.events[0].request_id == original.request_id
    assert evidence.events[0].action_id == original.action_id

    allowed_service, _ = _runtime_service(context)
    allowed_resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=(),
    )
    allowed = await allowed_service.require(ActionId.ACTOR_PROFILE_READ_SELF, allowed_resource)
    with pytest.raises(TypeError, match="invalid authorization denial evidence"):
        await allowed_service.restage_denial(allowed)

    other_service, _ = _runtime_service(context)
    with pytest.raises(TypeError, match="invalid authorization denial evidence"):
        await other_service.restage_denial(exc_info.value.decision)


@pytest.mark.parametrize(
    ("action", "resource_factory", "actor_kind", "expected"),
    [
        (
            ActionId.ACTOR_PROFILE_READ_SELF,
            lambda context: ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=uuid4(),
                requested_fields=(),
            ),
            ActorKind.HUMAN,
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        ),
        (
            ActionId.ACTOR_PROFILE_READ_SELF,
            lambda context: ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=("display_name",),
            ),
            ActorKind.HUMAN,
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        ),
        (
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            lambda context: ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=(),
            ),
            ActorKind.HUMAN,
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED,
        ),
        (
            ActionId.ACTOR_PROFILE_READ_SELF,
            lambda context: ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=(),
            ),
            ActorKind.SERVICE,
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
    ],
)
async def test_actor_self_guards_fail_closed(
    action: ActionId,
    resource_factory,
    actor_kind: ActorKind,
    expected: AuthorizationDenialCode,
) -> None:
    context = _runtime_context(actor_kind=actor_kind)

    async def revalidate(current, _resource):
        return current

    service, evidence = _runtime_service(context, revalidate=revalidate)
    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource_factory(context))
    assert exc_info.value.decision.denial_code is expected
    assert evidence.events[0].denial_code == expected.value


def test_authorization_decision_and_denial_reject_incoherent_outcomes() -> None:
    context = _runtime_context()
    base = {
        "decision_id": uuid4(),
        "action_id": ActionId.ACTOR_PROFILE_READ_SELF,
        "permission_id": PermissionId.ACTOR_PROFILE_READ_SELF,
        "resource_type": "actor_profile",
        "resource_id": context.actor_profile_id,
        "resource_context_digest": authorization_resource_digest(
            ActorSelfResourceContext(
                resource_type="actor_profile",
                resource_id=context.actor_profile_id,
                requested_fields=(),
            )
        ),
        "revalidated": False,
        "request_id": context.request_id,
        "correlation_id": context.correlation_id,
    }
    with pytest.raises(ValidationError):
        AuthorizationDecision(
            **base,
            allowed=True,
            denial_code=AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            matched_authority_kind=None,
        )
    with pytest.raises(ValidationError):
        AuthorizationDecision(
            **base,
            allowed=True,
            denial_code=None,
            matched_authority_kind=None,
        )
    with pytest.raises(ValidationError):
        AuthorizationDecision(
            **{**base, "permission_id": None},
            allowed=False,
            denial_code=AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            matched_authority_kind=None,
        )
    with pytest.raises(ValidationError, match="allowed decisions require"):
        AuthorizationDecision(
            **{**base, "action_id": None, "permission_id": None},
            allowed=True,
            denial_code=None,
            matched_authority_kind=MatchedAuthorityKind.ACTOR_SELF,
        )
    allowed = AuthorizationDecision(
        **base,
        allowed=True,
        denial_code=None,
        matched_authority_kind=MatchedAuthorityKind.ACTOR_SELF,
    )
    with pytest.raises(TypeError, match="requires a denied decision"):
        AuthorizationDenied(allowed)


async def test_authorization_state_is_not_cached_across_requests() -> None:
    active = _runtime_context()
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=active.actor_profile_id,
        requested_fields=(),
    )
    first, _ = _runtime_service(active)
    assert (await first.require(ActionId.ACTOR_PROFILE_READ_SELF, resource)).allowed is True
    revoked = active.model_copy(
        update={
            "identity_link_status": IdentityLinkStatus.REVOKED,
            "request_id": uuid4(),
            "correlation_id": uuid4(),
        }
    )
    second, _ = _runtime_service(revoked)
    with pytest.raises(AuthorizationDenied) as exc_info:
        await second.require(ActionId.ACTOR_PROFILE_READ_SELF, resource)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.IDENTITY_LINK_REVOKED


@pytest.mark.parametrize(
    ("actor_status", "link_status", "action", "expected"),
    [
        (
            ActorStatus.ACTIVE,
            IdentityLinkStatus.REVOKED,
            ActionId.ACTOR_PROFILE_READ_SELF,
            AuthorizationDenialCode.IDENTITY_LINK_REVOKED,
        ),
        (
            ActorStatus.DEACTIVATED,
            IdentityLinkStatus.ACTIVE,
            ActionId.ACTOR_PROFILE_READ_SELF,
            AuthorizationDenialCode.ACTOR_DEACTIVATED,
        ),
        (
            ActorStatus.SUSPENDED,
            IdentityLinkStatus.ACTIVE,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            AuthorizationDenialCode.ACTOR_SUSPENDED,
        ),
    ],
)
async def test_authorization_kernel_preserves_lifecycle_denial_precedence(
    actor_status: ActorStatus,
    link_status: IdentityLinkStatus,
    action: ActionId,
    expected: AuthorizationDenialCode,
) -> None:
    context = _runtime_context(actor_status=actor_status, link_status=link_status)

    async def revalidate(_context, _resource):
        return context

    service, evidence = _runtime_service(context, revalidate=revalidate)
    fields = ("display_name",) if action is ActionId.ACTOR_PROFILE_UPDATE_SELF else ()
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=fields,
    )

    with pytest.raises(AuthorizationDenied) as exc_info:
        await service.require(action, resource)

    assert exc_info.value.decision.denial_code is expected
    assert evidence.events[0].action_id is action
    assert evidence.events[0].denial_code == expected.value


async def test_actor_self_update_requires_transaction_revalidation() -> None:
    context = _runtime_context()
    read_resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=(),
    )
    resource = ActorSelfResourceContext(
        resource_type="actor_profile",
        resource_id=context.actor_profile_id,
        requested_fields=("contact_email",),
    )
    without_read_recheck, _ = _runtime_service(context, revalidate=None)
    with pytest.raises(AuthorizationDenied) as read_exc_info:
        await without_read_recheck.require(ActionId.ACTOR_PROFILE_READ_SELF, read_resource)
    assert read_exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED

    without_recheck, _ = _runtime_service(context, revalidate=None)
    with pytest.raises(AuthorizationDenied) as exc_info:
        await without_recheck.require(ActionId.ACTOR_PROFILE_UPDATE_SELF, resource)
    assert exc_info.value.decision.denial_code is AuthorizationDenialCode.RESOURCE_GUARD_DENIED

    calls = 0

    async def revalidate(current, supplied_resource):
        nonlocal calls
        calls += 1
        assert supplied_resource is resource
        return current

    service, evidence = _runtime_service(context, revalidate=revalidate)
    decision = await service.require(ActionId.ACTOR_PROFILE_UPDATE_SELF, resource)
    assert calls == 1
    assert decision.allowed is True
    assert decision.revalidated is True
    assert evidence.events[0].permission_id is PermissionId.ACTOR_PROFILE_UPDATE_SELF


@pytest.fixture
def authorization_database_env(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Ensure authorization tests use a clean current schema."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()


@pytest.fixture
async def authorization_factory(authorization_database_env: str):
    """Provide sessions and remove only rows created by this test module."""
    engine = create_async_engine(authorization_database_env)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("lock table authority_idempotency_records in access exclusive mode")
            )
            await connection.execute(text("lock table audit_events in access exclusive mode"))
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_reject_update_delete")
            )
            await connection.execute(
                text(
                    "alter table authority_idempotency_records disable trigger authority_idempotency_guard"
                )
            )
            await connection.execute(
                text(
                    "delete from audit_events where idempotency_reference is not null or denial_code='idempotency_mismatch'"
                )
            )
            await connection.execute(text("delete from authority_idempotency_records"))
            await connection.execute(
                text(
                    "alter table authority_idempotency_records enable trigger authority_idempotency_guard"
                )
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_reject_update_delete")
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_project_read_permissions_have_postgresql_role_scope_matrix(
    authorization_factory,
) -> None:
    """Prove persisted grants confer only the reviewed read projections."""
    now = datetime.now(UTC)
    project_id, other_project_id = uuid4(), uuid4()
    bootstrap_actor_id, bootstrap_link_id, bootstrap_grant_id = uuid4(), uuid4(), uuid4()
    role_cases = (
        (AdminRole.OPERATOR, AdminScope.SYSTEM, None, True),
        (AdminRole.PROJECT_MANAGER, AdminScope.PROJECT, project_id, True),
        (AdminRole.AUDIT_AUTHORITY, AdminScope.PROJECT, project_id, True),
        (AdminRole.FINANCE_AUTHORITY, AdminScope.PROJECT, project_id, False),
    )
    actor_cases = [(role, uuid4(), uuid4(), uuid4()) for role, *_rest in role_cases]
    contributor_cases = [(role, uuid4(), uuid4(), uuid4(), uuid4()) for role in ProjectRole]

    async with authorization_factory() as session:
        session.add_all(
            [
                ActorProfile(
                    id=str(bootstrap_actor_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(bootstrap_actor_id),
                ),
                ActorIdentityLink(
                    id=str(bootstrap_link_id),
                    actor_profile_id=str(bootstrap_actor_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"auth-11a-bootstrap-{bootstrap_actor_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(bootstrap_actor_id),
                    last_verified_at=now,
                ),
            ]
        )
        for _role, actor_id, link_id, _grant_id in actor_cases:
            session.add_all(
                [
                    ActorProfile(
                        id=str(actor_id),
                        actor_kind="human",
                        status="active",
                        provisioning_method="automatic_first_access",
                        created_by=str(actor_id),
                    ),
                    ActorIdentityLink(
                        id=str(link_id),
                        actor_profile_id=str(actor_id),
                        issuer="https://identity.flowresearch.tech",
                        subject=f"auth-11a-admin-{actor_id}",
                        subject_kind="human",
                        status="active",
                        linked_by=str(actor_id),
                        last_verified_at=now,
                    ),
                ]
            )
        for _role, actor_id, link_id, _snapshot_id, _grant_id in contributor_cases:
            session.add_all(
                [
                    ActorProfile(
                        id=str(actor_id),
                        actor_kind="human",
                        status="active",
                        provisioning_method="automatic_first_access",
                        created_by=str(actor_id),
                    ),
                    ActorIdentityLink(
                        id=str(link_id),
                        actor_profile_id=str(actor_id),
                        issuer="https://identity.flowresearch.tech",
                        subject=f"auth-11a-contributor-{actor_id}",
                        subject_kind="human",
                        status="active",
                        linked_by=str(actor_id),
                        last_verified_at=now,
                    ),
                ]
            )
        session.add(
            AdminRoleGrant(
                id=bootstrap_grant_id,
                target_actor_profile_id=str(bootstrap_actor_id),
                role=AdminRole.ACCESS_ADMINISTRATOR.value,
                scope_type=AdminScope.SYSTEM.value,
                status="active",
                version=1,
                granted_by_system_principal="workstream:system:bootstrap",
                grant_reason="AUTH-11A PostgreSQL bootstrap proof",
                granted_at=now,
            )
        )
        await session.flush()
        await session.execute(
            text(
                "update authority_control set bootstrap_completed=true, version=1, "
                "bootstrap_grant_id=:grant_id, updated_at=clock_timestamp() where id=1"
            ),
            {"grant_id": str(bootstrap_grant_id)},
        )
        await seed_authorized_project(
            session,
            project_id=str(project_id),
            name="AUTH-11A role matrix",
            slug=f"auth-11a-role-matrix-{project_id}",
        )
        await seed_authorized_project(
            session,
            project_id=str(other_project_id),
            name="AUTH-11A other project",
            slug=f"auth-11a-other-project-{other_project_id}",
        )
        for (role, scope, scope_project_id, _allowed), (
            _case_role,
            actor_id,
            _link_id,
            grant_id,
        ) in zip(role_cases, actor_cases, strict=True):
            session.add(
                AdminRoleGrant(
                    id=grant_id,
                    target_actor_profile_id=str(actor_id),
                    role=role.value,
                    scope_type=scope.value,
                    scope_project_id=(str(scope_project_id) if scope_project_id else None),
                    status="active",
                    version=1,
                    granted_by_actor_profile_id=str(bootstrap_actor_id),
                    granted_by_admin_role_grant_id=bootstrap_grant_id,
                    grant_reason=f"AUTH-11A PostgreSQL {role.value} proof",
                    granted_at=now,
                )
            )
        for role, actor_id, _link_id, snapshot_id, grant_id in contributor_cases:
            session.add(
                ProjectRoleQualificationSnapshot(
                    id=snapshot_id,
                    project_id=str(project_id),
                    actor_profile_id=str(actor_id),
                    requested_role=role.value,
                    **_project_role_qualification(),
                    captured_by_actor_profile_id=str(bootstrap_actor_id),
                    captured_by_admin_role_grant_id=bootstrap_grant_id,
                    captured_at=now,
                )
            )
        await session.flush()
        for role, actor_id, _link_id, snapshot_id, grant_id in contributor_cases:
            session.add(
                ProjectRoleGrant(
                    id=grant_id,
                    project_id=str(project_id),
                    actor_profile_id=str(actor_id),
                    role=role.value,
                    qualification_snapshot_id=snapshot_id,
                    granted_by_actor_profile_id=str(bootstrap_actor_id),
                    granted_by_admin_role_grant_id=bootstrap_grant_id,
                    grant_reason=f"AUTH-11A {role.value} exclusion proof",
                    granted_at=now,
                )
            )
        await session.commit()

        repository = AdminAuthorizationRepository(session)
        permissions = (
            PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ,
            PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
        )
        for (_role, scope, _scope_project_id, allowed), (
            _case_role,
            actor_id,
            _link_id,
            _grant_id,
        ) in zip(role_cases, actor_cases, strict=True):
            for permission in permissions:
                grant = await repository.find_effective_grant(
                    actor_id, permission, scope_project_id=project_id
                )
                assert (grant is not None) is allowed
                if allowed and scope is AdminScope.PROJECT:
                    assert (
                        await repository.find_effective_grant(
                            actor_id, permission, scope_project_id=other_project_id
                        )
                        is None
                    )
        for _role, actor_id, _link_id, _snapshot_id, _grant_id in contributor_cases:
            for permission in permissions:
                assert (
                    await repository.find_effective_grant(
                        actor_id, permission, scope_project_id=project_id
                    )
                    is None
                )
        for permission in permissions:
            assert (
                await repository.find_effective_grant(
                    bootstrap_actor_id, permission, scope_project_id=project_id
                )
                is None
            )


@pytest.mark.asyncio
async def test_authorization_locks_refresh_cached_actor_lifecycle_state(
    authorization_factory,
) -> None:
    """Locked authorization rows must replace stale identity-map state."""
    profile_id, link_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as seed:
        seed.add_all(
            [
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(profile_id),
                ),
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"lock-refresh-{profile_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(profile_id),
                    last_verified_at=now,
                ),
            ]
        )
        await seed.commit()

    async with authorization_factory() as stale:
        cached_profile = await stale.get(ActorProfile, str(profile_id))
        cached_link = await stale.get(ActorIdentityLink, str(link_id))
        assert cached_profile is not None and cached_profile.status == "active"
        assert cached_link is not None and cached_link.status == "active"

        async with authorization_factory() as lifecycle:
            await lifecycle.execute(
                text(
                    "update actor_profiles set status='suspended', "
                    "suspended_by=:actor, suspended_at=:changed_at, "
                    "suspension_reason='security hold' where id=:actor"
                ),
                {"actor": str(profile_id), "changed_at": now},
            )
            await lifecycle.execute(
                text(
                    "update actor_identity_links set status='revoked', "
                    "revoked_by=:actor, revoked_at=:changed_at, "
                    "revoked_reason='credential revoked' where id=:link"
                ),
                {"actor": str(profile_id), "changed_at": now, "link": str(link_id)},
            )
            await lifecycle.commit()

        locked = await AdminAuthorizationRepository(stale).lock_request_actor(
            link_id,
            profile_id,
        )
        assert locked is not None
        locked_link, locked_profile = locked
        assert locked_profile is cached_profile
        assert locked_link is cached_link
        assert locked_profile.status == "suspended"
        assert locked_link.status == "revoked"
        assert await AdminAuthorizationRepository(stale).lock_eligible_human(profile_id) is None
        await stale.rollback()

        cached_profile = await stale.get(ActorProfile, str(profile_id))
        cached_link = await stale.get(ActorIdentityLink, str(link_id))
        assert cached_profile is not None and cached_profile.status == "suspended"
        assert cached_link is not None and cached_link.status == "revoked"
        async with authorization_factory() as lifecycle:
            await lifecycle.execute(
                text(
                    "update actor_profiles set status='active', suspended_by=null, "
                    "suspended_at=null, suspension_reason=null, reactivated_by=:actor, "
                    "reactivated_at=:changed_at, reactivation_reason='security restored' "
                    "where id=:actor"
                ),
                {"actor": str(profile_id), "changed_at": now},
            )
            await lifecycle.execute(
                text(
                    "update actor_identity_links set status='active', revoked_by=null, "
                    "revoked_at=null, revoked_reason=null, reactivated_by=:actor, "
                    "reactivated_at=:changed_at, reactivation_reason='credential restored' "
                    "where id=:link"
                ),
                {"actor": str(profile_id), "changed_at": now, "link": str(link_id)},
            )
            await lifecycle.commit()

        eligible = await AdminAuthorizationRepository(stale).lock_eligible_human(profile_id)
        assert eligible is not None
        eligible_link, eligible_profile = eligible
        assert eligible_profile is cached_profile
        assert eligible_link is cached_link
        assert eligible_profile.status == "active"
        assert eligible_link.status == "active"
        await stale.rollback()

    async with authorization_factory() as cleanup:
        await cleanup.execute(text("alter table actor_profiles disable trigger user"))
        await cleanup.execute(text("alter table actor_identity_links disable trigger user"))
        await cleanup.execute(
            text(
                "update actor_profiles set reactivated_by=null,reactivated_at=null,"
                "reactivation_reason=null where id=:actor"
            ),
            {"actor": str(profile_id)},
        )
        await cleanup.execute(
            text(
                "update actor_identity_links set reactivated_by=null,reactivated_at=null,"
                "reactivation_reason=null where id=:link"
            ),
            {"link": str(link_id)},
        )
        await cleanup.execute(text("alter table actor_identity_links enable trigger user"))
        await cleanup.execute(text("alter table actor_profiles enable trigger user"))
        await cleanup.commit()


def _request(target: UUID | None = None) -> ActorProfileSuspendRequest:
    return ActorProfileSuspendRequest(
        operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        actor_profile_id=target or uuid4(),
        reason_digest=DIGEST,
    )


def _success(
    claim: AuthorityClaimHandle,
    request: ActorProfileSuspendRequest,
    *,
    request_id: UUID | None = None,
    correlation_id: UUID | None = None,
) -> AuthorityAuditEventInput:
    event_id = uuid4()
    return AuthorityAuditEventInput(
        event_id=event_id,
        event_type=AuthorityEventType.ACTOR_PROFILE_SUSPENDED,
        entity_type="actor_profile",
        entity_id=str(request.actor_profile_id),
        actor_ref_kind=claim.actor_ref_kind,
        actor_ref=claim.actor_ref,
        request_id=request_id or uuid4(),
        correlation_id=correlation_id or uuid4(),
        permission_id="actor.profile.suspend",
        resource_type="actor_profile",
        resource_id=str(request.actor_profile_id),
        target_ref_kind="actor_profile",
        target_ref_id=str(request.actor_profile_id),
        reason="security_response",
        idempotency_reference=claim.record_id,
        before_facts={"status": "active"},
        after_facts={"status": "suspended"},
    )


def _operation_success(
    claim: AuthorityClaimHandle,
    request,
    response: AuthorityResponseReference,
    *,
    admin_authorizer_grant_id: UUID | None = None,
    admin_revoke_target: UUID | None = None,
    identity_link_target: UUID | None = None,
) -> AuthorityAuditEventInput:
    """Build the exact concrete success evidence for one canonical operation case."""
    event, permission, reason = {
        AuthorityOperation.SERVICE_ACTOR_CREATE: (
            AuthorityEventType.SERVICE_ACTOR_PROVISIONED,
            "actor.service.provision",
            "manual_service_provisioning",
        ),
        AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE: (
            AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
            "admin_role.grant",
            "authority_assignment",
        ),
        AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE: (
            AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,
            "admin_role.revoke",
            "authority_revocation",
        ),
        AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE: (
            AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
            "project.role_grant.manage",
            "authority_assignment",
        ),
        AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE: (
            AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED,
            "project.role_grant.manage",
            "authority_revocation",
        ),
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: (
            AuthorityEventType.ACTOR_PROFILE_SUSPENDED,
            "actor.profile.suspend",
            "security_response",
        ),
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: (
            AuthorityEventType.ACTOR_PROFILE_REACTIVATED,
            "actor.profile.reactivate",
            "administrative_correction",
        ),
        AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: (
            AuthorityEventType.ACTOR_PROFILE_DEACTIVATED,
            "actor.profile.deactivate",
            "security_response",
        ),
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: (
            AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,
            "actor.identity_link.revoke",
            "identity_lifecycle_change",
        ),
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: (
            AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
            "actor.identity_link.reactivate",
            "identity_lifecycle_change",
        ),
    }[request.operation]
    before_facts = None
    after_facts = None
    project_id = None
    target_actor = None
    matched_grant = None
    if isinstance(request, ServiceActorCreateRequest):
        after_facts = {
            "status": "active",
            "subject_kind": "service",
            "provisioning_method": "manual_service_provisioning",
        }
    elif isinstance(request, AdminRoleGrantIssueRequest):
        if admin_authorizer_grant_id is None:
            raise AssertionError("admin issue proof requires the distinct authorizing grant")
        target_actor = request.target_actor_id
        matched_grant = admin_authorizer_grant_id
        project_id = request.scope_project_id
        after_facts = {
            "status": "active",
            "role": request.role.value,
            "scope_type": request.scope_type.value,
            "effective": True,
        }
        if project_id:
            after_facts["scope_id"] = str(project_id)
    elif isinstance(request, AdminRoleGrantRevokeRequest):
        if admin_authorizer_grant_id is None:
            raise AssertionError("admin revoke proof requires the distinct authorizing grant")
        if admin_revoke_target is None:
            raise AssertionError("admin revoke proof requires the distinct grant target")
        target_actor = admin_revoke_target
        matched_grant = admin_authorizer_grant_id
        before_facts = {
            "status": "active",
            "role": "access_administrator",
            "scope_type": "system",
            "effective": True,
        }
        after_facts = before_facts | {"status": "revoked", "effective": False}
    elif isinstance(request, ProjectRoleGrantIssueRequest):
        if admin_authorizer_grant_id is None:
            raise AssertionError("project role issue proof requires authorizing manager grant")
        project_id = request.project_id
        target_actor = request.target_actor_id
        matched_grant = admin_authorizer_grant_id
        after_facts = {
            "status": "active",
            "role": request.role.value,
            "scope_type": "project",
            "scope_id": str(project_id),
            "effective": True,
        }
    elif isinstance(request, ProjectRoleGrantRevokeRequest):
        if admin_authorizer_grant_id is None:
            raise AssertionError("project role revoke proof requires authorizing manager grant")
        project_id = request.project_id
        target_actor = response.resource_id
        matched_grant = admin_authorizer_grant_id
        before_facts = {
            "status": "active",
            "role": "submitter",
            "scope_type": "project",
            "scope_id": str(project_id),
            "effective": True,
        }
        after_facts = before_facts | {"status": "revoked", "effective": False}
    elif isinstance(request, ActorProfileSuspendRequest):
        before_facts, after_facts = {"status": "active"}, {"status": "suspended"}
    elif isinstance(request, ActorProfileReactivateRequest):
        before_facts, after_facts = {"status": "suspended"}, {"status": "active"}
    elif isinstance(request, ActorProfileDeactivateRequest):
        before_facts, after_facts = {"status": "active"}, {"status": "deactivated"}
    elif isinstance(request, ActorIdentityLinkRevokeRequest):
        if identity_link_target is None:
            raise AssertionError("identity-link revoke proof requires its owning actor")
        target_actor = identity_link_target
        before_facts, after_facts = {"status": "active"}, {"status": "revoked"}
    elif isinstance(request, ActorIdentityLinkReactivateRequest):
        if identity_link_target is None:
            raise AssertionError("identity-link reactivation proof requires its owning actor")
        target_actor = identity_link_target
        before_facts, after_facts = {"status": "revoked"}, {"status": "active"}

    event_id = uuid4()
    return AuthorityAuditEventInput(
        event_id=event_id,
        event_type=event,
        entity_type=response.resource_type.value,
        entity_id=str(response.resource_id),
        actor_ref_kind=claim.actor_ref_kind,
        actor_ref=claim.actor_ref,
        request_id=uuid4(),
        correlation_id=uuid4(),
        target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE if target_actor else None,
        target_actor_ref=str(target_actor) if target_actor else None,
        matched_grant_id=str(matched_grant) if matched_grant else None,
        permission_id=permission,
        project_id=str(project_id) if project_id else None,
        resource_type=response.resource_type.value,
        resource_id=str(response.resource_id),
        target_ref_kind=response.resource_type.value,
        target_ref_id=str(response.resource_id),
        reason=reason,
        idempotency_reference=claim.record_id,
        before_facts=before_facts,
        after_facts=after_facts,
    )


async def _claim(service: AuthorityMutationService, actor: UUID, key: UUID, request):
    result = await service.reserve(
        idempotency_key=key,
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor),
        request=request.model_dump(),
    )
    assert isinstance(result, ClaimedReservation)
    return result.claim


async def _complete(service, claim, request):
    success = _success(claim, request)
    response = AuthorityResponseReference(
        resource_type=AuthorityResourceType.ACTOR_PROFILE,
        resource_id=request.actor_profile_id,
        version=1,
        http_status=200,
    )
    result = await service.complete(
        claim=claim,
        request=request.model_dump(),
        response=response,
        success=success,
        invalidation=AuthorityInvalidationContext(
            event_id=uuid4(),
            request_id=success.request_id,
            correlation_id=success.correlation_id,
        ),
    )
    return result


@pytest.mark.asyncio
async def test_claim_completion_and_exact_replay_have_one_evidence_pair(
    authorization_factory,
) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        completed = await _complete(service, claim, request)
        await session.commit()

    async with authorization_factory() as session:
        replay = await AuthorityMutationService(session).reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor),
            request=request.model_dump(),
        )
        assert isinstance(replay, ReplayedReservation)
        assert replay.response == completed.response
        await session.commit()
        counts = (
            await session.execute(
                text(
                    "select event_type, count(*) from audit_events "
                    "where idempotency_reference=:record group by event_type order by event_type"
                ),
                {"record": claim.record_id},
            )
        ).all()
    assert counts == [("ActorProfileSuspended", 1), ("AuthorityInvalidationRequested", 1)]


@pytest.mark.asyncio
async def test_committed_record_rejects_additional_success_and_invalidation(
    authorization_factory,
) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        completed = await _complete(service, claim, request)
        await session.commit()

    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        extra_success = _success(claim, request)
        with pytest.raises(IntegrityError, match="committed authority idempotency is closed"):
            await service.complete(
                claim=claim,
                request=request.model_dump(),
                response=completed.response,
                success=extra_success,
                invalidation=AuthorityInvalidationContext(
                    event_id=uuid4(),
                    request_id=extra_success.request_id,
                    correlation_id=extra_success.correlation_id,
                ),
            )
        await session.rollback()

    async with authorization_factory() as session:
        cause_id = await session.scalar(
            text(
                "select id from audit_events where idempotency_reference=:id "
                "and event_type='ActorProfileSuspended'"
            ),
            {"id": claim.record_id},
        )
        context_id, request_id, correlation_id = uuid4(), uuid4(), uuid4()
        invalidation = AuthorityAuditEventInput(
            event_id=context_id,
            event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            entity_type="authority_invalidation",
            entity_id=str(context_id),
            actor_ref_kind=claim.actor_ref_kind,
            actor_ref=claim.actor_ref,
            request_id=request_id,
            correlation_id=correlation_id,
            permission_id="actor.profile.suspend",
            resource_type="actor_profile",
            resource_id=str(request.actor_profile_id),
            reason="authority_state_changed",
            idempotency_reference=claim.record_id,
            invalidation_cause_event_id=UUID(cause_id),
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=str(request.actor_profile_id),
            before_facts={"effective": True},
            after_facts={"effective": False},
        )
        with pytest.raises(IntegrityError, match="committed authority idempotency is closed"):
            await AuditService(session).add_authority_event(invalidation)
        await session.rollback()

    async with authorization_factory() as session:
        assert (
            await session.scalar(
                text("select count(*) from audit_events where idempotency_reference=:id"),
                {"id": claim.record_id},
            )
            == 2
        )


@pytest.mark.asyncio
async def test_completion_rejects_resource_and_project_not_bound_to_request(
    authorization_factory,
) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    wrong_request = _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        wrong_success = _success(claim, wrong_request)
        with pytest.raises(TypeError, match="invalid authority completion input"):
            await service.complete(
                claim=claim,
                request=request.model_dump(),
                response=AuthorityResponseReference(
                    resource_type=AuthorityResourceType.ACTOR_PROFILE,
                    resource_id=wrong_request.actor_profile_id,
                    http_status=200,
                ),
                success=wrong_success,
                invalidation=AuthorityInvalidationContext(
                    event_id=uuid4(),
                    request_id=wrong_success.request_id,
                    correlation_id=wrong_success.correlation_id,
                ),
            )
        await session.rollback()

    project_request = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=uuid4(),
        target_actor_id=uuid4(),
        role=ProjectRole.SUBMITTER,
        qualification=_project_role_qualification(),
        reason_digest=DIGEST,
    )
    wrong_project = project_request.model_copy(update={"project_id": uuid4()})
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, uuid4(), project_request)
        response = AuthorityResponseReference(
            resource_type=AuthorityResourceType.PROJECT_ROLE_GRANT,
            resource_id=uuid4(),
            http_status=201,
        )
        issued = _operation_success(
            claim,
            wrong_project,
            response,
            admin_authorizer_grant_id=uuid4(),
        )
        qualification_snapshot_id = uuid4()
        qualification = issued.model_copy(
            update={
                "event_id": uuid4(),
                "event_type": AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED,
                "entity_type": "qualification_snapshot",
                "entity_id": str(qualification_snapshot_id),
                "resource_type": "qualification_snapshot",
                "resource_id": str(qualification_snapshot_id),
                "target_ref_kind": "qualification_snapshot",
                "target_ref_id": str(qualification_snapshot_id),
                "reason": "qualification_evidence_captured",
                "after_facts": {"status": "captured"},
            }
        )
        with pytest.raises(TypeError, match="invalid authority completion input"):
            await service.complete(
                claim=claim,
                request=project_request.model_dump(),
                response=response,
                success=(qualification, issued),
                invalidation=None,
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_cross_actor_entity_and_cause_context_bypasses(
    authorization_factory,
) -> None:
    actor, request = uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, uuid4(), request)
        cross_actor = _success(claim, request).model_copy(update={"actor_ref": str(uuid4())})
        with pytest.raises(IntegrityError, match="idempotency reference"):
            await AuditService(session).add_authority_event(cross_actor)
        await session.rollback()

    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, uuid4(), request)
        wrong_entity = _success(claim, request).model_copy(
            update={"entity_type": "admin_role_grant"}
        )
        with pytest.raises(IntegrityError, match="success event does not match operation"):
            await AuditService(session).add_authority_event(wrong_entity)
        await session.rollback()

    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, uuid4(), request)
        success = _success(claim, request)
        await AuditService(session).add_authority_event(success)
        event_id = uuid4()
        wrong_context = AuthorityAuditEventInput(
            event_id=event_id,
            event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            entity_type="authority_invalidation",
            entity_id=str(event_id),
            actor_ref_kind=claim.actor_ref_kind,
            actor_ref=claim.actor_ref,
            request_id=uuid4(),
            correlation_id=success.correlation_id,
            permission_id="actor.profile.suspend",
            resource_type="actor_profile",
            resource_id=str(request.actor_profile_id),
            reason="authority_state_changed",
            idempotency_reference=claim.record_id,
            invalidation_cause_event_id=success.event_id,
            invalidation_target_kind="actor_profile",
            invalidation_target_ref=str(request.actor_profile_id),
            before_facts={"effective": True},
            after_facts={"effective": False},
        )
        with pytest.raises(IntegrityError, match="invalid linked authority cause"):
            await AuditService(session).add_authority_event(wrong_context)
        await session.rollback()


@pytest.mark.asyncio
async def test_pending_commit_fails_and_rollback_allows_retry(authorization_factory) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        await _claim(AuthorityMutationService(session), actor, key, request)
        with pytest.raises(DBAPIError, match="pending authority idempotency"):
            await session.commit()
        await session.rollback()
    async with authorization_factory() as session:
        result = await _claim(AuthorityMutationService(session), actor, key, request)
        assert result.request_digest.startswith("sha256:")
        await session.rollback()


@pytest.mark.asyncio
async def test_same_session_pending_and_forged_claim_fail_closed(authorization_factory) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        with pytest.raises(PendingAuthorityReservationError):
            await service.reserve(
                idempotency_key=key,
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor),
                request=request.model_dump(),
            )
        forged = claim.model_copy(update={"request_digest": "sha256:" + "b" * 64})
        with pytest.raises(InvalidAuthorityClaimError):
            await service._repository.complete(
                forged,
                AuthorityResponseReference(
                    resource_type=AuthorityResourceType.ACTOR_PROFILE,
                    resource_id=request.actor_profile_id,
                    http_status=200,
                ),
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_mismatch_is_private_and_denial_uses_clean_transaction(authorization_factory) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        await _complete(service, claim, request)
        await session.commit()
    different = _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        result = await service.reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor),
            request=different.model_dump(),
        )
        assert isinstance(result, MismatchedReservation)
        assert result.model_dump() == {"outcome": "mismatch"}
        await session.rollback()
        denial_id = await service.record_mismatch_denial(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor),
            request=different.model_dump(),
            context=AuthorityMismatchContext(
                event_id=uuid4(), request_id=uuid4(), correlation_id=uuid4()
            ),
        )
        await session.commit()
        denial = (
            await session.execute(
                text(
                    "select denial_code, idempotency_reference, resource_type, resource_id, "
                    "count(*) over () from audit_events where id=:id"
                ),
                {"id": str(denial_id)},
            )
        ).one()
        linked = await session.scalar(
            text(
                "select count(*) from audit_events where idempotency_reference=:id "
                "and event_type in ('ActorProfileSuspended','AuthorityInvalidationRequested')"
            ),
            {"id": claim.record_id},
        )
    assert denial == (
        "idempotency_mismatch",
        None,
        "actor_profile",
        str(different.actor_profile_id),
        1,
    )
    assert linked == 2


def test_request_admission_is_frozen_bounded_and_nonretaining() -> None:
    secret = "SECRET_AUTHORITY_INPUT_9f4b"
    source = UserDict(_request().model_dump())
    admitted = parse_authority_request(source)
    source["reason_digest"] = "sha256:" + "b" * 64
    assert admitted.reason_digest == DIGEST

    rejected = [
        {**_request().model_dump(), "reason_digest": secret},
        {**_request().model_dump(), "actor_profile_id": str(uuid4()).upper()},
        {**_request().model_dump(), "extra": secret},
    ]
    for value in rejected:
        with pytest.raises(TypeError, match="invalid authority mutation request") as caught:
            parse_authority_request(value)
        assert secret not in str(caught.value)
        assert secret not in repr(caught.value.args)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    for construct in (
        lambda: ActorProfileSuspendRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
            actor_profile_id=uuid4(),
            reason_digest=secret,
        ),
        lambda: ActorProfileSuspendRequest.model_validate(
            {
                "operation": AuthorityOperation.ACTOR_PROFILE_SUSPEND,
                "actor_profile_id": uuid4(),
                "reason_digest": secret,
            }
        ),
        lambda: ActorProfileSuspendRequest.model_validate_json(
            '{"operation":"actor_profile.suspend","actor_profile_id":"'
            + str(uuid4())
            + '","reason_digest":"'
            + secret
            + '"}'
        ),
        lambda: derive_reason_digest("\ud800" + secret),
        lambda: derive_service_identity_digest("https://identity.example", "\ud800" + secret),
        lambda: derive_service_identity_digest("\ud800" + secret, "service-subject"),
    ):
        with pytest.raises(TypeError) as caught:
            construct()
        assert secret not in str(caught.value)
        assert secret not in repr(caught.value.args)
        assert secret not in repr(caught.value.__dict__)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None


class _ChangingMapping(Mapping):
    def __init__(self, first: dict, second: dict) -> None:
        self.first, self.second, self.calls = first, second, 0

    def __iter__(self):
        return iter(self.first)

    def __len__(self):
        return len(self.first)

    def __getitem__(self, key):
        self.calls += 1
        return (self.first if self.calls == 1 else self.second)[key]


def test_state_changing_mapping_cannot_change_validated_snapshot() -> None:
    first = _request().model_dump()
    hostile = _ChangingMapping(first, {**first, "reason_digest": "not-a-digest"})
    with pytest.raises(TypeError, match="invalid authority mutation request"):
        parse_authority_request(hostile)


def _service_actor_request() -> ServiceActorCreateRequest:
    return ServiceActorCreateRequest(
        operation=AuthorityOperation.SERVICE_ACTOR_CREATE,
        service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
        identity_reference_digest=derive_service_identity_digest(
            "https://identity.flowresearch.tech", "opaque-service-subject"
        ),
        reason_digest=derive_reason_digest("Approved"),
    )


def _service_actor_decision(request: ServiceActorCreateRequest) -> AuthorizationDecision:
    resource = ServiceActorProvisionResourceContext(
        resource_type="service_actor_provisioning",
        resource_id=request.service_identity,
    )
    return AuthorizationDecision(
        decision_id=uuid4(),
        action_id=ActionId.ACTOR_SERVICE_PROVISION,
        permission_id=PermissionId.ACTOR_SERVICE_PROVISION,
        allowed=True,
        denial_code=None,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        resource_context_digest=authorization_resource_digest(resource),
        matched_authority_kind=MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=uuid4(),
        matched_scope_project_id=None,
        revalidated=True,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


async def test_service_actor_conflict_precedence_is_fixed_and_private() -> None:
    service = ServiceActorProvisioningService(object())  # type: ignore[arg-type]

    class Actors:
        profile = None
        link = None
        link_reads = 0

        async def get_service_actor(self, _service_identity):
            return self.profile

        async def get_identity_link(self, _issuer, _subject):
            self.link_reads += 1
            return self.link

    actors = Actors()
    service._actors = actors  # type: ignore[assignment]
    actors.profile = object()
    actors.link = object()
    assert (
        await service.find_conflict(
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            issuer="private-issuer",
            subject="private-subject",
        )
        is ServiceActorConflict.SERVICE_IDENTITY
    )
    assert actors.link_reads == 0

    actors.profile = None
    assert (
        await service.find_conflict(
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            issuer="private-issuer",
            subject="private-subject",
        )
        is ServiceActorConflict.EXTERNAL_IDENTITY
    )
    actors.link = None
    assert (
        await service.find_conflict(
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            issuer="private-issuer",
            subject="private-subject",
        )
        is None
    )


async def test_service_actor_replay_fails_closed_on_committed_state_drift() -> None:
    actor_id, creator_id = uuid4(), uuid4()
    request = _service_actor_request()
    response = AuthorityResponseReference(
        resource_type=AuthorityResourceType.ACTOR_PROFILE,
        resource_id=actor_id,
        version=None,
        http_status=201,
    )
    profile = ActorProfile(
        id=str(actor_id),
        actor_kind="service",
        status="active",
        provisioning_method="manual_service_provisioning",
        service_identity=request.service_identity.value,
        created_by=str(creator_id),
    )
    profile.created_at = datetime.now(UTC)
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=profile.id,
        issuer="https://identity.flowresearch.tech",
        subject="opaque-service-subject",
        subject_kind="service",
        status="active",
        linked_by=str(creator_id),
        last_verified_at=None,
    )
    link.linked_at = datetime.now(UTC)

    class Actors:
        current_profile = profile
        current_link = link

        async def get_actor_profile(self, _actor_profile_id):
            return self.current_profile

        async def get_identity_link_for_actor(self, _actor_profile_id):
            return self.current_link

    actors = Actors()
    service = ServiceActorProvisioningService(object())  # type: ignore[arg-type]
    service._actors = actors  # type: ignore[assignment]
    wrong_resource = response.model_copy(
        update={"resource_type": AuthorityResourceType.ADMIN_ROLE_GRANT}
    )
    with pytest.raises(TypeError, match="replay resource changed"):
        await service.replay_response(
            response=wrong_resource,
            request=request,
            issuer=link.issuer,
            subject=link.subject,
        )

    for current_profile in (
        None,
        profile.__class__(
            id=profile.id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by=profile.id,
        ),
        profile.__class__(
            id=profile.id,
            actor_kind="service",
            status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.ARTIFACT_SCHEDULER.value,
            created_by=profile.id,
        ),
        profile.__class__(
            id=profile.id,
            actor_kind="service",
            status="deactivated",
            provisioning_method="manual_service_provisioning",
            service_identity=profile.service_identity,
            created_by=profile.id,
            deactivated_by=profile.id,
            deactivated_at=datetime.now(UTC),
            deactivation_reason="retired",
        ),
    ):
        actors.current_profile = current_profile
        with pytest.raises(ServiceActorProvisioningUnavailable, match="actor is unavailable"):
            await service.replay_response(
                response=response,
                request=request,
                issuer=link.issuer,
                subject=link.subject,
            )

    actors.current_profile = profile
    for current_link in (
        None,
        link.__class__(
            id=link.id,
            actor_profile_id=profile.id,
            issuer="different-issuer",
            subject=link.subject,
            subject_kind="service",
            status="active",
            linked_by=link.linked_by,
        ),
        link.__class__(
            id=link.id,
            actor_profile_id=profile.id,
            issuer=link.issuer,
            subject="different-subject",
            subject_kind="service",
            status="active",
            linked_by=link.linked_by,
        ),
        link.__class__(
            id=link.id,
            actor_profile_id=profile.id,
            issuer=link.issuer,
            subject=link.subject,
            subject_kind="human",
            status="active",
            linked_by=link.linked_by,
            last_verified_at=datetime.now(UTC),
        ),
        link.__class__(
            id=link.id,
            actor_profile_id=profile.id,
            issuer=link.issuer,
            subject=link.subject,
            subject_kind="service",
            status="revoked",
            linked_by=link.linked_by,
            revoked_by=link.linked_by,
            revoked_at=datetime.now(UTC),
            revoked_reason="rotated",
        ),
    ):
        actors.current_link = current_link
        with pytest.raises(ServiceActorProvisioningUnavailable, match="link is unavailable"):
            await service.replay_response(
                response=response,
                request=request,
                issuer=link.issuer,
                subject=link.subject,
            )

    actors.current_link = link
    profile.created_at = None
    with pytest.raises(RuntimeError, match="creation facts are incomplete"):
        await service.replay_response(
            response=response,
            request=request,
            issuer=link.issuer,
            subject=link.subject,
        )
    profile.created_at = datetime.now(UTC)
    replayed = await service.replay_response(
        response=response,
        request=request,
        issuer=link.issuer,
        subject=link.subject,
    )
    assert replayed.actor_profile_id == actor_id
    assert replayed.service_identity is request.service_identity


async def test_service_actor_mutation_rejects_authority_and_request_drift_before_writes() -> None:
    actor_id = uuid4()
    request = _service_actor_request()
    decision = _service_actor_decision(request)
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=DIGEST,
    )
    service = ServiceActorProvisioningService(object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="exact matched authority"):
        await service.complete(
            claim=claim,
            request=request,
            decision=decision.model_copy(update={"revalidated": False}),
            actor_profile_id=actor_id,
            issuer="https://identity.flowresearch.tech",
            subject="opaque-service-subject",
            reason="Approved",
        )
    with pytest.raises(TypeError, match="identity digest changed"):
        await service.complete(
            claim=claim,
            request=request.model_copy(update={"identity_reference_digest": DIGEST}),
            decision=decision,
            actor_profile_id=actor_id,
            issuer="https://identity.flowresearch.tech",
            subject="opaque-service-subject",
            reason="Approved",
        )
    with pytest.raises(TypeError, match="reason digest changed"):
        await service.complete(
            claim=claim,
            request=request.model_copy(update={"reason_digest": DIGEST}),
            decision=decision,
            actor_profile_id=actor_id,
            issuer="https://identity.flowresearch.tech",
            subject="opaque-service-subject",
            reason="Approved",
        )
    invalid_decision = decision.model_copy(update={"revalidated": False})
    with pytest.raises(TypeError, match="mismatch requires exact matched authority"):
        await service.record_mismatch(
            actor_profile_id=actor_id,
            request=request,
            decision=invalid_decision,
        )
    with pytest.raises(TypeError, match="conflict requires exact matched authority"):
        await service.record_conflict(
            actor_profile_id=actor_id,
            request=request,
            decision=invalid_decision,
        )


def test_every_operation_has_one_strict_canonical_request_variant() -> None:
    project, actor, resource = uuid4(), uuid4(), uuid4()
    requests = [
        ServiceActorCreateRequest(
            operation=AuthorityOperation.SERVICE_ACTOR_CREATE,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            identity_reference_digest=derive_service_identity_digest(
                "https://identity.flowresearch.tech", "opaque-service-subject"
            ),
            reason_digest=derive_reason_digest("Approved"),
        ),
        AdminRoleGrantIssueRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
            target_actor_id=actor,
            role=AdminRole.PROJECT_MANAGER,
            scope_type=AdminScope.PROJECT,
            scope_project_id=project,
            reason_digest=derive_reason_digest("Assigned"),
        ),
        AdminRoleGrantRevokeRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
            grant_id=resource,
            reason_digest=DIGEST,
        ),
        ProjectRoleGrantIssueRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
            project_id=project,
            target_actor_id=actor,
            role=ProjectRole.ADJUDICATOR,
            qualification=_project_role_qualification(),
            reason_digest=DIGEST,
        ),
        ProjectRoleGrantRevokeRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
            project_id=project,
            grant_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileSuspendRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileReactivateRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_REACTIVATE,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileDeactivateRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_DEACTIVATE,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorIdentityLinkRevokeRequest(
            operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
            identity_link_id=resource,
            reason_digest=DIGEST,
        ),
        ActorIdentityLinkReactivateRequest(
            operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE,
            identity_link_id=resource,
            reason_digest=DIGEST,
        ),
    ]
    assert {parse_authority_request(item.model_dump()).operation for item in requests} == set(
        AuthorityOperation
    )


def test_project_role_contract_rejects_replacement_and_bounds_qualification_references() -> None:
    project_id, actor_id = uuid4(), uuid4()
    base = {
        "operation": "project_role_grant.issue",
        "project_id": project_id,
        "target_actor_id": actor_id,
        "role": "submitter",
        "reason_digest": DIGEST,
    }
    for invalid in (
        base | {"role": "both"},
        base | {"replaced_grant_id": uuid4()},
    ):
        with pytest.raises(TypeError, match="invalid authority mutation request"):
            parse_authority_request(invalid)

    available = {
        "availability": QualificationAvailability.AVAILABLE,
        "reference_ids": ["work:opaque-1"],
        "unavailable_reason": None,
    }
    unavailable = {
        "availability": QualificationAvailability.UNAVAILABLE,
        "reference_ids": [],
        "unavailable_reason": QualificationUnavailableReason.NO_RECORD,
    }
    snapshot = ProjectRoleQualificationSnapshotInput.model_validate(
        {
            "project_id": project_id,
            "actor_profile_id": actor_id,
            "requested_role": ProjectRole.ADJUDICATOR,
            "skills_snapshot": available,
            "reputation_snapshot": unavailable,
            "prior_project_work_refs": [uuid4()],
            "external_expertise_refs": ["expertise:opaque-1"],
        }
    )
    assert snapshot.requested_role is ProjectRole.ADJUDICATOR
    assert QualificationAvailabilitySnapshot.model_validate(available).reference_ids == [
        "work:opaque-1"
    ]
    for invalid in (
        available | {"reference_ids": []},
        available | {"unavailable_reason": "no_record"},
        unavailable | {"reference_ids": ["unexpected"]},
        available | {"reference_ids": ["https://credential.example/secret"]},
        available | {"reference_ids": ["x"] * 21},
    ):
        with pytest.raises(ValidationError):
            QualificationAvailabilitySnapshot.model_validate(invalid)


def test_project_role_qualification_evidence_rejects_coerced_values() -> None:
    available = QualificationAvailabilitySnapshot(
        availability=QualificationAvailability.AVAILABLE,
        reference_ids=["work:opaque-1"],
        unavailable_reason=None,
    )
    unavailable = QualificationAvailabilitySnapshot(
        availability=QualificationAvailability.UNAVAILABLE,
        reference_ids=[],
        unavailable_reason=QualificationUnavailableReason.NO_RECORD,
    )
    base = {
        "skills_snapshot": available,
        "reputation_snapshot": unavailable,
        "prior_project_work_refs": [uuid4()],
        "external_expertise_refs": ["expertise:opaque-1"],
    }
    assert ProjectRoleQualificationEvidence.model_validate(base).prior_project_work_refs
    canonical_string = str(uuid4())
    assert ProjectRoleQualificationEvidence.model_validate(
        base | {"prior_project_work_refs": [canonical_string]}
    ).prior_project_work_refs == [UUID(canonical_string)]
    for invalid in (
        base | {"prior_project_work_refs": [1]},
        base | {"prior_project_work_refs": [uuid4().bytes]},
        base | {"external_expertise_refs": [1]},
        base | {"external_expertise_refs": [b"expertise:opaque-1"]},
    ):
        with pytest.raises(ValidationError):
            ProjectRoleQualificationEvidence.model_validate(invalid)


def test_actor_profile_lifecycle_public_schemas_are_strict_bounded_and_typed() -> None:
    target = uuid4()
    assert ActorLifecycleBody(reason="  approved correction  ").reason == "approved correction"
    assert ActorLifecycleBody(reason="\tapproved correction\n").reason == "approved correction"
    assert ActorLifecycleBody(reason="\u00a0approved correction\u00a0").reason == (
        "approved correction"
    )
    assert ActorLifecycleBody(reason="é" * 250).reason == "é" * 250
    for value in ("", "   ", "contains\x00null", "é" * 251, "x" * 501, 1, None):
        with pytest.raises(ValidationError):
            ActorLifecycleBody.model_validate({"reason": value})
    with pytest.raises(ValidationError):
        ActorLifecycleBody.model_validate({"reason": "valid", "unexpected": True})
    assert ActorLifecycleMutationResponse(
        resource_type="actor_profile",
        resource_id=target,
        version=None,
        http_status=200,
    ).model_dump() == {
        "resource_type": "actor_profile",
        "resource_id": target,
        "version": None,
        "http_status": 200,
    }
    with pytest.raises(ValidationError):
        ActorLifecycleMutationResponse.model_validate(
            {
                "resource_type": "actor_profile",
                "resource_id": str(target),
                "version": None,
                "http_status": 200,
            }
        )


@pytest.mark.asyncio
async def test_project_role_and_all_operation_mappings_commit_one_linked_pair(
    authorization_factory,
) -> None:
    project, actor, resource, admin_revoke_target = uuid4(), uuid4(), uuid4(), uuid4()
    identity_link_target = uuid4()
    admin_authorizer_grant_id = uuid4()
    requests = [
        ServiceActorCreateRequest(
            operation=AuthorityOperation.SERVICE_ACTOR_CREATE,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            identity_reference_digest=derive_service_identity_digest(
                "https://identity.flowresearch.tech", "opaque-service-subject"
            ),
            reason_digest=derive_reason_digest("Approved"),
        ),
        AdminRoleGrantIssueRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
            target_actor_id=actor,
            role=AdminRole.PROJECT_MANAGER,
            scope_type=AdminScope.PROJECT,
            scope_project_id=project,
            reason_digest=DIGEST,
        ),
        AdminRoleGrantRevokeRequest(
            operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
            grant_id=resource,
            reason_digest=DIGEST,
        ),
        ProjectRoleGrantRevokeRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
            project_id=project,
            grant_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileSuspendRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileReactivateRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_REACTIVATE,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorProfileDeactivateRequest(
            operation=AuthorityOperation.ACTOR_PROFILE_DEACTIVATE,
            actor_profile_id=resource,
            reason_digest=DIGEST,
        ),
        ActorIdentityLinkRevokeRequest(
            operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
            identity_link_id=resource,
            reason_digest=DIGEST,
        ),
        ActorIdentityLinkReactivateRequest(
            operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE,
            identity_link_id=resource,
            reason_digest=DIGEST,
        ),
    ]
    resource_types = {
        AuthorityOperation.SERVICE_ACTOR_CREATE: AuthorityResourceType.ACTOR_PROFILE,
        AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE: AuthorityResourceType.ADMIN_ROLE_GRANT,
        AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE: AuthorityResourceType.ADMIN_ROLE_GRANT,
        AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE: AuthorityResourceType.PROJECT_ROLE_GRANT,
        AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE: AuthorityResourceType.PROJECT_ROLE_GRANT,
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: AuthorityResourceType.ACTOR_PROFILE,
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: AuthorityResourceType.ACTOR_PROFILE,
        AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: AuthorityResourceType.ACTOR_PROFILE,
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: AuthorityResourceType.ACTOR_IDENTITY_LINK,
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: AuthorityResourceType.ACTOR_IDENTITY_LINK,
    }
    create_operations = {
        AuthorityOperation.SERVICE_ACTOR_CREATE,
        AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
    }
    admin_operations = {
        AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
    }
    expected_pairs = {}
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        for request in requests:
            claim = await _claim(service, uuid4(), uuid4(), request)
            response_id = (
                uuid4()
                if request.operation in create_operations
                else getattr(
                    request,
                    "grant_id",
                    getattr(
                        request, "actor_profile_id", getattr(request, "identity_link_id", None)
                    ),
                )
            )
            response = AuthorityResponseReference(
                resource_type=resource_types[request.operation],
                resource_id=response_id,
                version=1,
                http_status=201 if request.operation in create_operations else 200,
            )
            success = _operation_success(
                claim,
                request,
                response,
                admin_authorizer_grant_id=(
                    admin_authorizer_grant_id if request.operation in admin_operations else None
                ),
                admin_revoke_target=(
                    admin_revoke_target
                    if request.operation is AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE
                    else None
                ),
                identity_link_target=(
                    identity_link_target
                    if request.operation
                    in {
                        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
                        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE,
                    }
                    else None
                ),
            )
            if request.operation is AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE:
                assert success.target_actor_ref == str(admin_revoke_target)
            if request.operation in admin_operations:
                assert success.matched_grant_id == str(admin_authorizer_grant_id)
                assert success.matched_grant_id != str(response.resource_id)
            success_input = success
            invalidation = AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=success.request_id,
                correlation_id=success.correlation_id,
                target_ref_kind=(
                    AuthorityResourceType.PROJECT_ROLE_GRANT
                    if request.operation is AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE
                    else None
                ),
                target_ref_id=(
                    response.resource_id
                    if request.operation is AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE
                    else None
                ),
                project_role=(
                    ProjectRole.SUBMITTER
                    if request.operation is AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE
                    else None
                ),
                future_obligation=(
                    "auth13_assignment"
                    if request.operation is AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE
                    else None
                ),
            )
            completed = await service.complete(
                claim=claim,
                request=request.model_dump(),
                response=response,
                success=success_input,
                invalidation=invalidation,
            )
            assert completed.response == response
            expected_pairs[claim.record_id] = success
            await session.commit()
        rows = (
            await session.execute(
                text(
                    "select id, event_type, idempotency_reference, "
                    "invalidation_cause_event_id, request_id, correlation_id, "
                    "target_actor_ref_kind,target_actor_ref,target_ref_kind,target_ref_id,"
                    "invalidation_target_ref,before_facts,after_facts "
                    "from audit_events "
                    "where idempotency_reference = any(:records) "
                    "order by idempotency_reference, event_type"
                ),
                {"records": list(expected_pairs)},
            )
        ).all()
    assert len(rows) == len(requests) * 2
    for record_id, success in expected_pairs.items():
        pair = [row for row in rows if row.idempotency_reference == record_id]
        assert len(pair) == 2
        success_row = next(row for row in pair if row.event_type == success.event_type.value)
        invalidation_row = next(
            row for row in pair if row.event_type == "AuthorityInvalidationRequested"
        )
        assert invalidation_row.invalidation_cause_event_id == success_row.id
        assert {(row.request_id, row.correlation_id) for row in pair} == {
            (success.request_id, success.correlation_id)
        }
        expected_target = (
            success.target_actor_ref
            if success.event_type
            in {
                AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
                AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,
                AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,
                AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
            }
            else success.resource_id
        )
        assert invalidation_row.invalidation_target_ref == expected_target
        if success.event_type is AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED:
            assert invalidation_row.target_actor_ref_kind == "actor_profile"
            assert invalidation_row.target_actor_ref == success.target_actor_ref
            assert invalidation_row.target_ref_kind == "project_role_grant"
            assert invalidation_row.target_ref_id == success.resource_id
        expected_before = (
            {"effective": False}
            if success.event_type
            in {
                AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
                AuthorityEventType.ACTOR_PROFILE_REACTIVATED,
                AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
            }
            else {"effective": True}
        )
        if success.event_type is AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED:
            expected_before = {
                "effective": True,
                "role": "submitter",
                "scope_type": "project",
                "scope_id": success.project_id,
                "future_obligation": "auth13_assignment",
            }
        expected_after = {"effective": not expected_before["effective"]}
        if success.event_type is AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED:
            expected_after = expected_before | {"effective": False}
        assert invalidation_row.before_facts == expected_before
        assert invalidation_row.after_facts == expected_after


async def test_project_role_issue_shared_completion_writes_ordered_zero_invalidation_pair() -> None:
    project_id, actor_id, target_id, grant_id, snapshot_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    request = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=project_id,
        target_actor_id=target_id,
        role=ProjectRole.SUBMITTER,
        qualification=_project_role_qualification(),
        reason_digest=DIGEST,
    )
    claim = AuthorityClaimHandle(
        record_id=uuid4(),
        idempotency_key=uuid4(),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(actor_id),
        operation=request.operation,
        request_digest=canonical_json_hash(request.model_dump(mode="json", exclude_none=True)),
    )
    response = AuthorityResponseReference(
        resource_type=AuthorityResourceType.PROJECT_ROLE_GRANT,
        resource_id=grant_id,
        version=1,
        http_status=201,
    )
    issued = _operation_success(
        claim,
        request,
        response,
        admin_authorizer_grant_id=uuid4(),
    )
    qualification = issued.model_copy(
        update={
            "event_id": uuid4(),
            "event_type": AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED,
            "entity_type": "qualification_snapshot",
            "entity_id": str(snapshot_id),
            "resource_type": "qualification_snapshot",
            "resource_id": str(snapshot_id),
            "target_ref_kind": "qualification_snapshot",
            "target_ref_id": str(snapshot_id),
            "reason": "qualification_evidence_captured",
            "after_facts": {"status": "captured"},
        }
    )

    class Audit:
        def __init__(self) -> None:
            self.events = []

        async def add_authority_event(self, event):
            self.events.append(event)
            return SimpleNamespace(id=str(event.event_id))

    class Repository:
        completed = None

        async def complete(self, completed_claim, completed_response):
            self.completed = (completed_claim, completed_response)

    service = AuthorityMutationService(object())  # type: ignore[arg-type]
    audit = Audit()
    repository = Repository()
    service._audit = audit  # type: ignore[assignment]
    service._repository = repository  # type: ignore[assignment]

    result = await service.complete(
        claim=claim,
        request=request.model_dump(),
        response=response,
        success=(qualification, issued),
        invalidation=None,
    )

    assert [event.event_type for event in audit.events] == [
        AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED,
        AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
    ]
    assert repository.completed == (claim, response)
    assert result.invalidation_event_id is None


@pytest.mark.asyncio
async def test_issue_mismatch_derives_project_and_omits_nonexistent_grant_resource(
    authorization_factory,
) -> None:
    project = uuid4()
    request = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=project,
        target_actor_id=uuid4(),
        role=ProjectRole.REVIEWER,
        qualification=_project_role_qualification(),
        reason_digest=DIGEST,
    )
    context = AuthorityMismatchContext(event_id=uuid4(), request_id=uuid4(), correlation_id=uuid4())
    async with authorization_factory() as session:
        event_id = await AuthorityMutationService(session).record_mismatch_denial(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(uuid4()),
            request=request.model_dump(),
            context=context,
        )
        await session.commit()
        row = (
            await session.execute(
                text(
                    "select project_id, resource_type, resource_id from audit_events where id=:id"
                ),
                {"id": str(event_id)},
            )
        ).one()
    assert row == (str(project), None, None)


@pytest.mark.asyncio
async def test_failure_after_evidence_flush_rolls_back_claim_and_events(
    authorization_factory, monkeypatch
) -> None:
    actor, key, request = uuid4(), uuid4(), _request()
    async with authorization_factory() as session:
        service = AuthorityMutationService(session)
        claim = await _claim(service, actor, key, request)
        synthetic_id = uuid4()
        await service.record_mismatch_denial(
            actor_ref_kind=claim.actor_ref_kind,
            actor_ref=claim.actor_ref,
            request=request.model_dump(),
            context=AuthorityMismatchContext(
                event_id=synthetic_id,
                request_id=uuid4(),
                correlation_id=uuid4(),
            ),
        )

        async def fail_completion(*_args, **_kwargs):
            raise RuntimeError("injected completion failure")

        monkeypatch.setattr(service._repository, "complete", fail_completion)
        with pytest.raises(RuntimeError, match="injected completion failure"):
            await _complete(service, claim, request)
        await session.rollback()
    async with authorization_factory() as session:
        assert (
            await session.scalar(
                text("select count(*) from authority_idempotency_records where id=:id"),
                {"id": claim.record_id},
            )
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where idempotency_reference=:id"),
                {"id": claim.record_id},
            )
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from audit_events where id=:id"),
                {"id": str(synthetic_id)},
            )
            == 0
        )


async def _wait_for_database_lock(database_url: str, application_name: str) -> None:
    """Observe the loser waiting on PostgreSQL rather than using a timing sleep."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            deadline = monotonic() + 5.0
            while monotonic() < deadline:
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_stat_activity where "
                        "application_name=:name and wait_event_type='Lock')"
                    ),
                    {"name": application_name},
                )
                if waiting:
                    return
                await asyncio.sleep(0.01)
    finally:
        await engine.dispose()
    raise AssertionError("concurrent reservation never reached the database lock")


@pytest.mark.asyncio
async def test_concurrent_exact_and_mismatched_retries_serialize_at_unique_namespace(
    authorization_database_env: str,
    authorization_factory,
) -> None:
    del authorization_factory  # fixture owns immutable-row cleanup
    actor, key, request = uuid4(), uuid4(), _request()
    winner_engine = create_async_engine(
        authorization_database_env,
        connect_args={"server_settings": {"application_name": "auth05b-winner"}},
    )
    loser_engine = create_async_engine(
        authorization_database_env,
        connect_args={"server_settings": {"application_name": "auth05b-loser"}},
    )
    winner_factory = async_sessionmaker(winner_engine, expire_on_commit=False)
    loser_factory = async_sessionmaker(loser_engine, expire_on_commit=False)

    async def lose(candidate):
        async with loser_factory() as session:
            return await AuthorityMutationService(session).reserve(
                idempotency_key=key,
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor),
                request=candidate.model_dump(),
            )

    try:
        async with winner_factory() as winner:
            service = AuthorityMutationService(winner)
            claim = await _claim(service, actor, key, request)
            loser = asyncio.create_task(lose(request))
            await asyncio.wait_for(
                _wait_for_database_lock(authorization_database_env, "auth05b-loser"),
                timeout=5,
            )
            await _complete(service, claim, request)
            await winner.commit()
        assert isinstance(await asyncio.wait_for(loser, timeout=5), ReplayedReservation)

        key = uuid4()
        async with winner_factory() as winner:
            service = AuthorityMutationService(winner)
            claim = await _claim(service, actor, key, request)
            loser = asyncio.create_task(lose(_request()))
            await asyncio.wait_for(
                _wait_for_database_lock(authorization_database_env, "auth05b-loser"),
                timeout=5,
            )
            await _complete(service, claim, request)
            await winner.commit()
        assert isinstance(await asyncio.wait_for(loser, timeout=5), MismatchedReservation)
    finally:
        await winner_engine.dispose()
        await loser_engine.dispose()


@pytest.mark.asyncio
async def test_same_key_is_isolated_independently_by_actor_and_reference_kind(
    authorization_factory,
) -> None:
    key, request = uuid4(), _request()
    actor = str(uuid4())
    async with (
        authorization_factory() as first,
        authorization_factory() as second,
        authorization_factory() as third,
    ):
        one = await AuthorityMutationService(first).reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=actor,
            request=request.model_dump(),
        )
        two = await AuthorityMutationService(second).reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.LEGACY_ACTOR,
            actor_ref=actor,
            request=request.model_dump(),
        )
        three = await AuthorityMutationService(third).reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(uuid4()),
            request=request.model_dump(),
        )
        assert isinstance(one, ClaimedReservation)
        assert isinstance(two, ClaimedReservation)
        assert isinstance(three, ClaimedReservation)
        await first.rollback()
        await second.rollback()
        await third.rollback()


@pytest.mark.asyncio
async def test_project_role_issue_postgresql_prep_binds_target_role_and_scope(
    authorization_database_env: str,
    authorization_factory,
    monkeypatch,
) -> None:
    caller_id, caller_link_id, target_id, target_link_id, project_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    manager_grant_id = uuid4()
    bootstrap_grant_id = uuid4()
    now = datetime.now(UTC)
    async with authorization_factory() as session:
        session.add_all(
            [
                ActorProfile(
                    id=str(caller_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(caller_id),
                ),
                ActorIdentityLink(
                    id=str(caller_link_id),
                    actor_profile_id=str(caller_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"auth10c-caller-{caller_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(caller_id),
                    last_verified_at=now,
                ),
                ActorProfile(
                    id=str(target_id),
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=str(target_id),
                ),
                ActorIdentityLink(
                    id=str(target_link_id),
                    actor_profile_id=str(target_id),
                    issuer="https://identity.flowresearch.tech",
                    subject=f"auth10c-target-{target_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=str(target_id),
                    last_verified_at=now,
                ),
                AdminRoleGrant(
                    id=bootstrap_grant_id,
                    target_actor_profile_id=str(caller_id),
                    role="access_administrator",
                    scope_type="system",
                    scope_project_id=None,
                    status="active",
                    version=1,
                    granted_by_actor_profile_id=None,
                    granted_by_system_principal="workstream:system:bootstrap",
                    granted_by_admin_role_grant_id=None,
                    grant_reason="AUTH-10C PostgreSQL bootstrap proof",
                ),
            ]
        )
        await session.flush()
        await session.execute(
            text(
                "update authority_control set bootstrap_completed=true, version=1, "
                "bootstrap_grant_id=:grant_id, updated_at=clock_timestamp() where id=1"
            ),
            {"grant_id": str(bootstrap_grant_id)},
        )
        await session.commit()
        await seed_authorized_project(
            session,
            project_id=str(project_id),
            name="AUTH-10C PREP proof",
            slug=f"auth-10c-prep-{project_id}",
        )
        await session.commit()
        session.add(
            AdminRoleGrant(
                id=manager_grant_id,
                target_actor_profile_id=str(caller_id),
                role="project_manager",
                scope_type="project",
                scope_project_id=str(project_id),
                status="active",
                version=1,
                granted_by_actor_profile_id=str(caller_id),
                granted_by_system_principal=None,
                granted_by_admin_role_grant_id=bootstrap_grant_id,
                grant_reason="AUTH-10C PostgreSQL project-manager proof",
            )
        )
        await session.commit()
        context = HumanAuthorizationContext(
            actor_profile_id=caller_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=caller_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        repository = AdminAuthorizationRepository(session)
        authorization = AuthorizationService(session, context, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, context, authorization, repository)
        issue_reason = "AUTH-10C PostgreSQL issue proof"
        canonical_issue = ProjectRoleGrantIssueRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
            project_id=project_id,
            target_actor_id=target_id,
            role=ProjectRole.SUBMITTER,
            qualification=_project_role_qualification(),
            reason_digest=derive_reason_digest(issue_reason),
        )
        issue_key = uuid4()
        await session.begin()
        issue_reservation = await ProjectRoleGrantMutationService(session).reserve(
            key=issue_key,
            actor_profile_id=caller_id,
            request=canonical_issue,
        )
        assert isinstance(issue_reservation, ClaimedReservation)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=issue_key, request_value=canonical_issue.model_dump(mode="json")
        )
        handle = await prepared.prepare(
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            caller_input,
            PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=project_id,
                target_actor_profile_id=target_id,
                role=ProjectRole.SUBMITTER,
            ),
        )
        assert await repository.lock_project(project_id) is not None
        await repository.take_project_role_issue_lock(
            project_role_issue_lock_key(target_id, project_id, "submitter")
        )
        assert await repository.lock_eligible_human(target_id) is not None
        issue_resource = ProjectRoleGrantIssueResourceContext(
            resource_type="project_role_grant",
            resource_id=project_id,
            scope_project_id=project_id,
            target_actor_profile_id=target_id,
            role=ProjectRole.SUBMITTER,
            project_status="draft",
            target_eligible=True,
            active_exact_role_exists=False,
        )
        decision = await prepared.consume(
            handle, ActionId.PROJECT_ROLE_GRANT_ISSUE, caller_input, issue_resource
        )
        assert decision.allowed is True
        assert decision.matched_grant_id == manager_grant_id
        issue_service = ProjectRoleGrantMutationService(session)
        for substituted in (
            decision.model_copy(update={"action_id": ActionId.PROJECT_ROLE_GRANT_REVOKE}),
            decision.model_copy(update={"permission_id": PermissionId.PROJECT_READ}),
            decision.model_copy(update={"revalidated": False}),
            decision.model_copy(update={"matched_scope_project_id": uuid4()}),
            decision.model_copy(update={"resource_context_digest": f"sha256:{'0' * 64}"}),
        ):
            with pytest.raises(TypeError, match="requires exact matched authority"):
                await issue_service.complete_issue(
                    claim=issue_reservation.claim,
                    request=canonical_issue,
                    decision=substituted,
                    resource=issue_resource,
                    actor_profile_id=caller_id,
                    reason=issue_reason,
                )
        issued = await issue_service.complete_issue(
            claim=issue_reservation.claim,
            request=canonical_issue,
            decision=decision,
            resource=issue_resource,
            actor_profile_id=caller_id,
            reason=issue_reason,
        )
        assert issued.status == "active"
        await session.commit()
        await session.execute(
            text(
                "update actor_profiles set status='suspended', suspended_by=:by, "
                "suspended_at=clock_timestamp(), suspension_reason=:reason where id=:id"
            ),
            {"id": str(target_id), "by": str(caller_id), "reason": "AUTH-10C proof"},
        )
        await session.execute(
            text(
                "update actor_identity_links set status='revoked', revoked_by=:by, "
                "revoked_at=clock_timestamp(), revoked_reason=:reason where id=:id"
            ),
            {"id": str(target_link_id), "by": str(caller_id), "reason": "AUTH-10C proof"},
        )
        await session.commit()
        revoke_reason = "AUTH-10C lifecycle-independent revoke proof"
        canonical_revoke = ProjectRoleGrantRevokeRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
            project_id=project_id,
            grant_id=issued.id,
            reason_digest=derive_reason_digest(revoke_reason),
        )
        revoke_key = uuid4()
        revoke_reservation = await ProjectRoleGrantMutationService(session).reserve(
            key=revoke_key,
            actor_profile_id=caller_id,
            request=canonical_revoke,
        )
        assert isinstance(revoke_reservation, ClaimedReservation)
        revoke_input = PreparedAuthorizationInput(
            idempotency_key=revoke_key,
            request_value=canonical_revoke.model_dump(mode="json"),
        )
        revoke_handle = await prepared.prepare(
            ActionId.PROJECT_ROLE_GRANT_REVOKE,
            revoke_input,
            PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=project_id,
                grant_id=issued.id,
            ),
        )
        project = await repository.lock_project(project_id)
        row = await repository.lock_project_role_grant(project_id=project_id, grant_id=issued.id)
        assert project is not None and row is not None
        grant, _snapshot = row
        revoke_resource = ProjectRoleGrantRevokeResourceContext(
            resource_type="project_role_grant",
            resource_id=issued.id,
            scope_project_id=project_id,
            actor_profile_id=target_id,
            role=ProjectRole.SUBMITTER,
            project_status="draft",
            status="active",
            version=1,
        )
        revoke_decision = await prepared.consume(
            revoke_handle,
            ActionId.PROJECT_ROLE_GRANT_REVOKE,
            revoke_input,
            revoke_resource,
        )
        revoke_service = ProjectRoleGrantMutationService(session)
        for substituted_decision, substituted_resource in (
            (
                revoke_decision.model_copy(update={"action_id": ActionId.PROJECT_ROLE_GRANT_ISSUE}),
                revoke_resource,
            ),
            (
                revoke_decision.model_copy(update={"permission_id": PermissionId.PROJECT_READ}),
                revoke_resource,
            ),
            (revoke_decision.model_copy(update={"revalidated": False}), revoke_resource),
            (
                revoke_decision.model_copy(update={"matched_scope_project_id": uuid4()}),
                revoke_resource,
            ),
            (
                revoke_decision.model_copy(
                    update={"resource_context_digest": f"sha256:{'0' * 64}"}
                ),
                revoke_resource,
            ),
            (
                revoke_decision,
                revoke_resource.model_copy(update={"actor_profile_id": uuid4()}),
            ),
            (
                revoke_decision,
                revoke_resource.model_copy(update={"role": ProjectRole.REVIEWER}),
            ),
            (
                revoke_decision,
                revoke_resource.model_copy(update={"version": 2, "status": "revoked"}),
            ),
        ):
            with pytest.raises(TypeError, match="requires exact matched authority"):
                await revoke_service.complete_revoke(
                    claim=revoke_reservation.claim,
                    request=canonical_revoke,
                    decision=substituted_decision,
                    resource=substituted_resource,
                    actor_profile_id=caller_id,
                    reason=revoke_reason,
                    grant=grant,
                )
        assert grant.status == "active"
        assert grant.version == 1
        revoked = await revoke_service.complete_revoke(
            claim=revoke_reservation.claim,
            request=canonical_revoke,
            decision=revoke_decision,
            resource=revoke_resource,
            actor_profile_id=caller_id,
            reason=revoke_reason,
            grant=grant,
        )
        assert revoked.status == "revoked"
        await session.commit()
        assert (
            await session.scalar(
                text(
                    "select count(*) from audit_events where idempotency_reference in (:issue, :revoke)"
                ),
                {
                    "issue": str(issue_reservation.claim.record_id),
                    "revoke": str(revoke_reservation.claim.record_id),
                },
            )
            == 4
        )
        revoke_invalidation = (
            await session.execute(
                text(
                    "select target_actor_ref_kind,target_actor_ref,resource_type,resource_id,"
                    "target_ref_kind,target_ref_id,invalidation_target_kind,"
                    "invalidation_target_ref,before_facts,after_facts "
                    "from audit_events where idempotency_reference=:revoke "
                    "and event_type='AuthorityInvalidationRequested'"
                ),
                {"revoke": str(revoke_reservation.claim.record_id)},
            )
        ).one()
        assert tuple(revoke_invalidation[:8]) == (
            "actor_profile",
            str(target_id),
            "project_role_grant",
            str(issued.id),
            "project_role_grant",
            str(issued.id),
            "project_role_grant",
            str(issued.id),
        )
        assert revoke_invalidation.before_facts == {
            "effective": True,
            "role": "submitter",
            "scope_type": "project",
            "scope_id": str(project_id),
            "future_obligation": "auth13_assignment",
        }
        assert revoke_invalidation.after_facts == {
            **revoke_invalidation.before_facts,
            "effective": False,
        }

        await session.execute(
            text(
                "update actor_profiles set status='active', suspended_by=null, "
                "suspended_at=null, suspension_reason=null, reactivated_by=:by, "
                "reactivated_at=clock_timestamp(), reactivation_reason=:reason where id=:id"
            ),
            {
                "id": str(target_id),
                "by": str(caller_id),
                "reason": "AUTH-10C continuation proof",
            },
        )
        await session.execute(
            text(
                "update actor_identity_links set status='active', revoked_by=null, "
                "revoked_at=null, revoked_reason=null, reactivated_by=:by, "
                "reactivated_at=clock_timestamp(), reactivation_reason=:reason where id=:id"
            ),
            {
                "id": str(target_link_id),
                "by": str(caller_id),
                "reason": "AUTH-10C continuation proof",
            },
        )
        qualification = _project_role_qualification()
        existing_snapshot = ProjectRoleQualificationSnapshot(
            id=uuid4(),
            project_id=str(project_id),
            actor_profile_id=str(target_id),
            requested_role="reviewer",
            skills_snapshot=qualification["skills_snapshot"],
            reputation_snapshot=qualification["reputation_snapshot"],
            prior_project_work_refs=[],
            external_expertise_refs=[],
            captured_by_actor_profile_id=str(caller_id),
            captured_by_admin_role_grant_id=manager_grant_id,
        )
        session.add(existing_snapshot)
        await session.flush()
        session.add(
            ProjectRoleGrant(
                id=uuid4(),
                project_id=str(project_id),
                actor_profile_id=str(target_id),
                role="reviewer",
                status="active",
                version=1,
                grant_method="manual",
                qualification_snapshot_id=existing_snapshot.id,
                granted_by_actor_profile_id=str(caller_id),
                granted_by_admin_role_grant_id=manager_grant_id,
                grant_reason="AUTH-10C unique-index winner",
            )
        )
        await session.commit()

        race_reason = "AUTH-10C real unique-index loser"
        race_payload = ProjectRoleGrantIssueBody(
            target_actor_profile_id=target_id,
            role=ProjectRole.REVIEWER,
            qualification=_project_role_qualification(),
            reason=race_reason,
        )
        race_key = uuid4()
        original_find = AdminAuthorizationRepository.find_active_project_role
        original_reserve = ProjectRoleGrantMutationService.reserve
        find_calls = 0
        race_claim_ids: list[UUID] = []

        async def race_find(repository, **kwargs):
            nonlocal find_calls
            find_calls += 1
            if find_calls == 1:
                return None
            return await original_find(repository, **kwargs)

        async def capture_race_claim(service, **kwargs):
            reservation = await original_reserve(service, **kwargs)
            assert isinstance(reservation, ClaimedReservation)
            race_claim_ids.append(reservation.claim.record_id)
            return reservation

        monkeypatch.setattr(AdminAuthorizationRepository, "find_active_project_role", race_find)
        monkeypatch.setattr(ProjectRoleGrantMutationService, "reserve", capture_race_claim)
        caller_profile = await session.get(ActorProfile, str(caller_id))
        caller_link = await session.get(ActorIdentityLink, str(caller_link_id))
        assert caller_profile is not None and caller_link is not None
        with pytest.raises(StructuredHTTPException) as conflict:
            await authorization_router.issue_project_role_grant(
                project_id=project_id,
                payload=race_payload,
                idempotency_key=race_key,
                resolved=ResolvedActor(caller_profile, caller_link),
                prepared=prepared,
                session=session,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.error_code == "project_role_grant_exists"
        assert find_calls == 2
        assert len(race_claim_ids) == 1
        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "find_active_project_role",
            original_find,
        )
        monkeypatch.setattr(
            ProjectRoleGrantMutationService,
            "reserve",
            original_reserve,
        )
        prepared.close()

    async with authorization_factory() as clean:
        assert (
            await clean.scalar(
                text(
                    "select count(*) from project_role_grants where project_id=:project "
                    "and actor_profile_id=:actor and role='reviewer' and status='active'"
                ),
                {"project": str(project_id), "actor": str(target_id)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from project_role_qualification_snapshots "
                    "where project_id=:project and actor_profile_id=:actor "
                    "and requested_role='reviewer'"
                ),
                {"project": str(project_id), "actor": str(target_id)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from authority_idempotency_records where idempotency_key=:key"
                ),
                {"key": str(race_key)},
            )
            == 0
        )
        denial_rows = (
            await clean.execute(
                text(
                    "select event_type, denial_code, idempotency_reference from audit_events "
                    "where request_id=:request and correlation_id=:correlation "
                    "and action_id='project_role_grant.issue'"
                ),
                {
                    "request": str(context.request_id),
                    "correlation": str(context.correlation_id),
                },
            )
        ).all()
        assert (
            denial_rows.count(("SensitiveAuthorizationDenied", "project_role_grant_exists", None))
            == 1
        )
        assert all(row[0] != "AuthorityInvalidationRequested" for row in denial_rows)
        assert (
            await clean.scalar(
                text("select count(*) from audit_events where idempotency_reference=:claim"),
                {"claim": str(race_claim_ids[0])},
            )
            == 0
        )
        await clean.rollback()

    canonical = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=project_id,
        target_actor_id=target_id,
        role=ProjectRole.SUBMITTER,
        qualification=_project_role_qualification(),
        reason_digest=derive_reason_digest("AUTH-10C concurrency proof"),
    )
    waiting_key = uuid4()
    async with authorization_factory() as locker, authorization_factory() as waiter:
        locker_repository = AdminAuthorizationRepository(locker)
        locker_authorization = AuthorizationService(
            locker, context, admin_repository=locker_repository
        )
        locker_prepared = PreparedAuthorizationService(
            locker, context, locker_authorization, locker_repository
        )
        waiter_repository = AdminAuthorizationRepository(waiter)
        waiter_authorization = AuthorizationService(
            waiter, context, admin_repository=waiter_repository
        )
        waiter_prepared = PreparedAuthorizationService(
            waiter, context, waiter_authorization, waiter_repository
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=project_id,
            target_actor_profile_id=target_id,
            role=ProjectRole.SUBMITTER,
        )
        await locker.begin()
        await locker_prepared.prepare(
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            PreparedAuthorizationInput(
                idempotency_key=uuid4(), request_value=canonical.model_dump(mode="json")
            ),
            scope,
        )
        await waiter.begin()
        await ProjectRoleGrantMutationService(waiter).reserve(
            key=waiting_key,
            actor_profile_id=caller_id,
            request=canonical,
        )
        waiter_pid = await waiter.scalar(text("select pg_backend_pid()"))
        wait_task = asyncio.create_task(
            authorization_router._database_call(
                waiter,
                waiter_prepared.prepare(
                    ActionId.PROJECT_ROLE_GRANT_ISSUE,
                    PreparedAuthorizationInput(
                        idempotency_key=waiting_key,
                        request_value=canonical.model_dump(mode="json"),
                    ),
                    scope,
                ),
            )
        )
        observer = create_async_engine(authorization_database_env)
        try:
            async with observer.connect() as connection:
                deadline = monotonic() + 5.0
                while monotonic() < deadline:
                    waiting = await connection.scalar(
                        text(
                            "select exists(select 1 from pg_stat_activity where "
                            "pid=:pid and wait_event_type='Lock')"
                        ),
                        {"pid": waiter_pid},
                    )
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("PREP contender never waited on its database lock")
        finally:
            await observer.dispose()
        wait_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await wait_task
        await locker.rollback()

        retry_reservation = await ProjectRoleGrantMutationService(waiter).reserve(
            key=waiting_key,
            actor_profile_id=caller_id,
            request=canonical,
        )
        assert isinstance(retry_reservation, ClaimedReservation)
        retry_input = PreparedAuthorizationInput(
            idempotency_key=waiting_key,
            request_value=canonical.model_dump(mode="json"),
        )
        retry_handle = await authorization_router._database_call(
            waiter,
            waiter_prepared.prepare(
                ActionId.PROJECT_ROLE_GRANT_ISSUE,
                retry_input,
                scope,
            ),
        )
        waiter_repository = AdminAuthorizationRepository(waiter)
        project = await waiter_repository.lock_project(project_id)
        assert project is not None
        await waiter_repository.take_project_role_issue_lock(
            project_role_issue_lock_key(target_id, project_id, "submitter")
        )
        assert await waiter_repository.lock_eligible_human(target_id) is not None
        assert (
            await waiter_repository.find_active_project_role(
                project_id=project_id,
                actor_profile_id=target_id,
                role="submitter",
            )
            is None
        )
        retry_resource = ProjectRoleGrantIssueResourceContext(
            resource_type="project_role_grant",
            resource_id=project_id,
            scope_project_id=project_id,
            target_actor_profile_id=target_id,
            role=ProjectRole.SUBMITTER,
            project_status=project.status,
            target_eligible=True,
            active_exact_role_exists=False,
        )
        retry_decision = await waiter_prepared.consume(
            retry_handle,
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            retry_input,
            retry_resource,
        )
        retried = await ProjectRoleGrantMutationService(waiter).complete_issue(
            claim=retry_reservation.claim,
            request=canonical,
            decision=retry_decision,
            resource=retry_resource,
            actor_profile_id=caller_id,
            reason="AUTH-10C concurrency proof",
        )
        await waiter.commit()
        assert retried.status == "active"
        waiter_prepared.close()
        locker_prepared.close()
    async with authorization_factory() as clean:
        assert (
            await clean.scalar(
                text(
                    "select count(*) from authority_idempotency_records where idempotency_key=:key"
                ),
                {"key": str(waiting_key)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from audit_events where "
                    "idempotency_reference=(select id from authority_idempotency_records "
                    "where idempotency_key=:key)"
                ),
                {"key": str(waiting_key)},
            )
            == 2
        )
        await clean.rollback()
