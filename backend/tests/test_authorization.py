from __future__ import annotations

import ast
import asyncio
import base64
from collections import UserDict
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api.deps.authorization import get_authorization_actor, get_authorization_service
from app.core.api_controls import StructuredHTTPException
from app.core.config import get_settings
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ActorService
from app.modules.actors.service_identities import SERVICE_IDENTITIES, ServiceIdentity
from app.modules.authorization import catalogue as authorization_catalogue
from app.modules.authorization import kernel as authorization_kernel
from app.modules.authorization import router as authorization_router
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
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    ReplayedReservation,
    ServiceActorCreateRequest,
    derive_reason_digest,
    derive_service_identity_digest,
    parse_authority_request,
)
from app.modules.authorization.service import AuthorityMutationService
from app.modules.authorization.kernel import AuthorizationService
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
    ActorIdentityLinkAdminReadResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
    ActorKind,
    ActorProfileAdminReadResourceContext,
    ActorProfileLifecycleResourceContext,
    ActorSelfResourceContext,
    ActorStatus,
    AdminRoleDefinitionsResourceContext,
    AdminRoleGrantCollectionResourceContext,
    AdminRoleGrantIssueResourceContext,
    AdminRoleGrantResourceContext,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    MatchedAuthorityKind,
    PermissionCatalogueResourceContext,
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
        "planned",
    ),
    "artifact.pending_work.scan": (
        "artifact.pending_work.scan",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "planned",
    ),
    "artifact.put_attempt.resolve": (
        "artifact.put_attempt.resolve",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "planned",
    ),
    "artifact.guide_source.ingest": (
        "artifact.guide_source.ingest",
        "WS-AUTH-001-ART-03",
        "planned",
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
    "artifact.upload_session.create": (
        "artifact.upload_session.create",
        "WS-AUTH-001-ART-04A",
        "planned",
    ),
    "artifact.upload_session.read": (
        "artifact.upload_session.read",
        "WS-AUTH-001-ART-04A",
        "planned",
    ),
    "artifact.upload_item.write": (
        "artifact.upload_item.write",
        "WS-AUTH-001-ART-04A",
        "planned",
    ),
    "artifact.upload_session.seal": (
        "artifact.upload_session.seal",
        "WS-AUTH-001-ART-04A",
        "planned",
    ),
    "artifact.upload_session.cancel": (
        "artifact.upload_session.cancel",
        "WS-AUTH-001-ART-04A",
        "planned",
    ),
    "artifact.upload_session.expire": (
        "artifact.upload_session.expire",
        "WS-AUTH-001-ART-04A",
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
        """operations.task.start_override operations.submission_gate.repair
        operations.checker.retry artifact.binding.read artifact.replica.read
        artifact.receipt.read artifact.verification_job.read
        artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read
        artifact.guide_source.ingest artifact.upload_session.create
        artifact.upload_session.read artifact.upload_item.write artifact.upload_session.seal
        artifact.upload_session.cancel artifact.upload_session.expire artifact.binding.create
        artifact.verification.execute artifact.pending_work.scan artifact.put_attempt.resolve
        artifact.guide_source.read artifact.checker_input.materialize
        artifact.checker_output.write review.queue.override""".split()
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
    }
    assert {item.value for item in HISTORICAL_PERMISSION_IDS} == historical_permissions
    assert {item.value for item in NEW_PERMISSION_IDS} == new_permissions
    assert {item.value for item in PERMISSION_IDS} == historical_permissions | new_permissions
    assert len(ACTION_IDS) == len(ACTION_DEFINITIONS) == len(ACTION_BY_ID) == 65
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
            ActionOwner.AUTH_ART_04A,
            ActionOwner.AUTH_ART_04B,
            ActionOwner.AUTH_ART_05,
            ActionOwner.AUTH_ART_06A,
            ActionOwner.AUTH_ART_06B,
        }
    } == {
        ActionOwner.AUTH_ART_02D_OPERATOR: 8,
        ActionOwner.AUTH_ART_02D_INTERNAL: 3,
        ActionOwner.AUTH_ART_03: 3,
        ActionOwner.AUTH_ART_04A: 6,
        ActionOwner.AUTH_ART_04B: 1,
        ActionOwner.AUTH_ART_05: 1,
        ActionOwner.AUTH_ART_06A: 1,
        ActionOwner.AUTH_ART_06B: 2,
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
    assert sum(
        definition.availability is ActionAvailability.ACTIVE
        for definition in ACTION_DEFINITIONS
    ) == 17
    assert sum(
        definition.availability is ActionAvailability.PLANNED
        for definition in ACTION_DEFINITIONS
    ) == 48
    assert resolve_executable_action(ActionId.ACTOR_PROFILE_READ_SELF).permission_id is (
        PermissionId.ACTOR_PROFILE_READ_SELF
    )
    with pytest.raises(ValueError, match="not active"):
        resolve_executable_action(ActionId.REVIEW_QUEUE_READ)
    with pytest.raises(TypeError):
        ACTION_BY_ID[ActionId.ACTOR_PROFILE_READ_SELF] = ACTION_DEFINITIONS[0]


def test_fixed_service_action_matrix_is_exact_planned_and_immutable() -> None:
    expected = {
        ServiceIdentity.ARTIFACT_VERIFIER: {"artifact.verification.execute"},
        ServiceIdentity.ARTIFACT_PUT_RESOLVER: {"artifact.put_attempt.resolve"},
        ServiceIdentity.ARTIFACT_SCHEDULER: {
            "artifact.pending_work.scan",
            "artifact.upload_session.expire",
        },
        ServiceIdentity.ARTIFACT_BINDING: {
            "artifact.guide_source.binding.create",
            "artifact.submission.binding.create",
            "artifact.checker_output.binding.create",
        },
        ServiceIdentity.ARTIFACT_GUIDE_READER: {"artifact.guide_source.read"},
        ServiceIdentity.ARTIFACT_MATERIALIZER: {
            "artifact.pre_submit.checker_input.materialize",
            "artifact.post_submit.checker_input.materialize",
        },
        ServiceIdentity.ARTIFACT_CHECKER_OUTPUT: {"artifact.checker_output.write"},
    }
    assert set(SERVICE_ACTIONS_BY_IDENTITY) == SERVICE_IDENTITIES
    assert {
        identity: {action.value for action in actions}
        for identity, actions in SERVICE_ACTIONS_BY_IDENTITY.items()
    } == expected
    assert sum(map(len, SERVICE_ACTIONS_BY_IDENTITY.values())) == 11
    assert all(
        ACTION_BY_ID[action].availability is ActionAvailability.PLANNED
        for actions in SERVICE_ACTIONS_BY_IDENTITY.values()
        for action in actions
    )
    with pytest.raises(TypeError):
        SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.ARTIFACT_VERIFIER] = frozenset()  # type: ignore[index]


def _parse_custody_table(document: Path, expected_actions: set[str]) -> dict[str, str]:
    rows = document.read_text(encoding="utf-8").splitlines()
    for header_index, row in enumerate(rows):
        if row not in {
            "| AUTH activation custodian | Exact planned ActionIds |",
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
        "WS-AUTH-001-ART-03": 3,
        "WS-AUTH-001-ART-04A": 6,
        "WS-AUTH-001-ART-04B": 1,
        "WS-AUTH-001-ART-05": 1,
        "WS-AUTH-001-ART-06A": 1,
        "WS-AUTH-001-ART-06B": 2,
    }

    for document in custody_documents:
        parsed = _parse_custody_table(document, set(expected_custody))
        assert parsed == expected_custody
        assert {
            owner: sum(parsed_owner == owner for parsed_owner in parsed.values())
            for owner in set(parsed.values())
        } == expected_owner_counts

    spec_rows = (repository_root / "docs/spec_authorization_service.md").read_text(
        encoding="utf-8"
    ).splitlines()
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
    assert "all 25 ART rows to eight exact AUTH custodians" in operations
    assert "all 19 REV\nrows to seven exact AUTH custodians" in operations
    assert "The ART transfer adds no migration" in operations
    assert "does not grant Operator" in operations
    assert "verification retry remains independently gated" in operations
    assert "74 PermissionIds, 65 ActionIds, 17 active actions, and\n48 planned actions" in operations


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

    spec_rows = (repository_root / "docs/spec_authorization_service.md").read_text(
        encoding="utf-8"
    ).splitlines()
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
        changed = replace(definition, availability=ActionAvailability.ACTIVE)
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
        AdminRole.OPERATOR: """project.read review.queue.inspect review.lease.force_release
            contribution.read_project compensation.award.read operations.status.read
            operations.timer.run operations.reconcile.run operations.outbox.retry
            operations.projection.rebuild operations.task.start_override
            operations.submission_gate.repair operations.checker.retry artifact.binding.read
            artifact.replica.read artifact.receipt.read artifact.verification_job.read
            artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read
            audit.read""".split(),
        AdminRole.PROJECT_MANAGER: """project.create project.read project.update project.archive
            project.guide.manage project.effective_policy.manage project.task.manage
            project.review_policy.manage project.role_grant.read project.role_grant.manage
            review.queue.inspect contribution.read_project compensation.award.read
            audit.read""".split(),
        AdminRole.FINANCE_AUTHORITY: """project.read contribution.read_project
            compensation.policy.manage compensation.adapter_binding.manage
            compensation.award.read compensation.delivery.reconcile audit.read""".split(),
        AdminRole.AUDIT_AUTHORITY: """actor.profile.read_any actor.identity_link.read
            admin_role.read project.read project.role_grant.read review.queue.inspect
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
    assert permission_response.total == 74
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
        assert response.updates == [
            {"last_verified_at": resolved.identity_link.last_verified_at}
        ]


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

    session = Session()
    with pytest.raises(StructuredHTTPException) as commit_failure:
        await authorization_router._commit_or_unavailable(session)
    with pytest.raises(StructuredHTTPException) as query_failure:
        await authorization_router._database_call(session, failed_operation())

    for failure in (commit_failure.value, query_failure.value):
        assert failure.status_code == 503
        assert failure.error_code == "service_unavailable"
        assert failure.retryable is True
    assert session.commits == 1
    assert session.rollbacks == 2


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
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    ActionOwner.AUTH_ART_02D_OPERATOR,
                    ActionAvailability.PLANNED,
                ),
            ),
            "metadata mismatch",
        ),
        (
            ACTION_DEFINITIONS[:-1]
            + (
                ActionDefinition(
                    ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
                    ActionOwner.AUTH_ART_06B,
                    ActionAvailability.ACTIVE,
                ),
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
            definitions[first_index], owner="WS-REV-001-05"  # type: ignore[arg-type]
        )
        message = "invalid row"
    elif mutation == "wrong_custodian":
        definitions[first_index] = replace(
            definitions[first_index], owner=ActionOwner.AUTH_REV_12
        )
        message = "metadata mismatch"
    elif mutation == "swapped_custodians":
        definitions[first_index] = replace(
            definitions[first_index], owner=ActionOwner.AUTH_REV_06
        )
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
) -> AuthorizationContext:
    context_type = (
        ServiceAuthorizationContext
        if actor_kind is ActorKind.SERVICE
        else HumanAuthorizationContext
    )
    service_fields = (
        {"service_identity": ServiceIdentity.ARTIFACT_VERIFIER}
        if actor_kind is ActorKind.SERVICE
        else {}
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
    revalidate=_DEFAULT_REVALIDATOR,
    revalidate_service=None,
) -> tuple[AuthorizationService, _DecisionEvidence]:
    if revalidate is _DEFAULT_REVALIDATOR:

        async def revalidate(current, _resource):
            return current

    service = AuthorizationService(
        object(),  # type: ignore[arg-type]
        context,
        revalidate_actor_self=revalidate,
        revalidate_service=revalidate_service,
    )
    evidence = _DecisionEvidence()
    service._audit = evidence  # type: ignore[assignment]
    return service, evidence


class _AdminPolicyFacts:
    """Configurable canonical facts for focused kernel policy tests."""

    def __init__(self, context: AuthorizationContext) -> None:
        self.context = context
        self.matched = SimpleNamespace(id=uuid4())
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

    crossed = self_resource.model_copy(
        update={"resource_id": uuid4(), "transition": "deactivate"}
    )
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

    crossed = self_revoke.model_copy(
        update={"resource_id": uuid4(), "transition": "reactivate"}
    )
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
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: (
            PermissionId.ACTOR_IDENTITY_LINK_REVOKE
        ),
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
    revoke_claim = issue_claim.model_copy(
        update={"operation": revoke_request.operation}
    )
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
            decision=revoke_decision.model_copy(
                update={"resource_context_digest": normal_digest}
            ),
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
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
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
        await dependency.athrow(exc_info.value)

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
        await dependency.athrow(asyncio.CancelledError())

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
    assert public_methods == {"require"}
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
            expected = (
                AuthorizationDenialCode.ACTION_UNAVAILABLE
                if action in own_actions
                else AuthorizationDenialCode.PERMISSION_NOT_GRANTED
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


@pytest.mark.parametrize(
    ("actor_status", "link_status", "expected"),
    [
        (ActorStatus.ACTIVE, IdentityLinkStatus.REVOKED, AuthorizationDenialCode.IDENTITY_LINK_REVOKED),
        (ActorStatus.SUSPENDED, IdentityLinkStatus.ACTIVE, AuthorizationDenialCode.ACTOR_SUSPENDED),
        (ActorStatus.DEACTIVATED, IdentityLinkStatus.ACTIVE, AuthorizationDenialCode.ACTOR_DEACTIVATED),
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
        ("suspended", "active", ServiceIdentity.ARTIFACT_VERIFIER.value, AuthorizationDenialCode.ACTOR_SUSPENDED),
        ("deactivated", "active", ServiceIdentity.ARTIFACT_VERIFIER.value, AuthorizationDenialCode.ACTOR_DEACTIVATED),
        ("active", "revoked", ServiceIdentity.ARTIFACT_VERIFIER.value, AuthorizationDenialCode.IDENTITY_LINK_REVOKED),
        ("active", "active", ServiceIdentity.ARTIFACT_SCHEDULER.value, AuthorizationDenialCode.PERMISSION_NOT_GRANTED),
        ("active", "active", "malformed-service-identity", AuthorizationDenialCode.PERMISSION_NOT_GRANTED),
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
                    action: replace(active_actions[action], availability=ActionAvailability.PLANNED),
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
    {**ART_CUSTODY_EXPECTATIONS, **REV_CUSTODY_EXPECTATIONS}.items(),
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

    await service._restage_denial(exc_info.value.decision)

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
        await allowed_service._restage_denial(allowed)

    other_service, _ = _runtime_service(context)
    with pytest.raises(TypeError, match="invalid authorization denial evidence"):
        await other_service._restage_denial(exc_info.value.decision)


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
    assert (
        read_exc_info.value.decision.denial_code
        is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    )

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
    postgres_database_url: str,
    migration_lock,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Ensure authorization tests run at the current isolated schema head."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    with migration_lock():
        command.upgrade(config, "head")
    yield postgres_database_url
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
        assert (
            await AdminAuthorizationRepository(stale).lock_eligible_human(profile_id)
            is None
        )
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

        eligible = await AdminAuthorizationRepository(stale).lock_eligible_human(
            profile_id
        )
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
            AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED
            if getattr(request, "replaced_grant_id", None)
            else AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
            "project.role_grant.manage",
            "authority_replacement"
            if getattr(request, "replaced_grant_id", None)
            else "authority_assignment",
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
        project_id = request.project_id
        target_actor = request.target_actor_id
        matched_grant = request.replaced_grant_id
        after_facts = {
            "status": "active",
            "role": request.role.value,
            "scope_type": "project",
            "scope_id": str(project_id),
            "effective": True,
        }
        if matched_grant:
            before_facts = after_facts | {"role": "reviewer"}
    elif isinstance(request, ProjectRoleGrantRevokeRequest):
        project_id = request.project_id
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
        success = _operation_success(claim, wrong_project, response)
        with pytest.raises(TypeError, match="invalid authority completion input"):
            await service.complete(
                claim=claim,
                request=project_request.model_dump(),
                response=response,
                success=success,
                invalidation=AuthorityInvalidationContext(
                    event_id=uuid4(),
                    request_id=success.request_id,
                    correlation_id=success.correlation_id,
                ),
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
            role=ProjectRole.BOTH,
            replaced_grant_id=resource,
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
async def test_all_operation_and_replacement_mappings_commit_one_linked_pair(
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
        ProjectRoleGrantIssueRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
            project_id=project,
            target_actor_id=actor,
            role=ProjectRole.SUBMITTER,
            reason_digest=DIGEST,
        ),
        ProjectRoleGrantIssueRequest(
            operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
            project_id=project,
            target_actor_id=actor,
            role=ProjectRole.SUBMITTER,
            replaced_grant_id=resource,
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
        AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
    }
    admin_operations = {
        AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
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
            completed = await service.complete(
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
            assert completed.response == response
            expected_pairs[claim.record_id] = success
            await session.commit()
        rows = (
            await session.execute(
                text(
                    "select id, event_type, idempotency_reference, "
                    "invalidation_cause_event_id, request_id, correlation_id, "
                    "invalidation_target_ref, before_facts, after_facts "
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
        assert {
            (row.request_id, row.correlation_id) for row in pair
        } == {(success.request_id, success.correlation_id)}
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
        expected_after = {"effective": not expected_before["effective"]}
        assert invalidation_row.before_facts == expected_before
        assert invalidation_row.after_facts == expected_after


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
            for _ in range(5000):
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_stat_activity where "
                        "application_name=:name and wait_event_type='Lock')"
                    ),
                    {"name": application_name},
                )
                if waiting:
                    return
                await asyncio.sleep(0)
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
