"""Prepared, idempotent project-role grant mutations."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy.sql import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import integrity_constraint_name

from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.models import ProjectRoleGrant, ProjectRoleQualificationSnapshot
from app.modules.authorization.project_role_schemas import ProjectRoleGrantMutationResponse
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDecision,
    MatchedAuthorityKind,
    ProjectRoleGrantIssueResourceContext,
    ProjectRoleGrantRevokeResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.schemas import (
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    ProjectRole,
    derive_reason_digest,
)
from app.modules.authorization.service import AuthorityMutationService


class ProjectRoleGrantConflict(RuntimeError):
    def __init__(self, code: str, grant_id: UUID | None) -> None:
        self.code = code
        self.grant_id = grant_id
        super().__init__(code)


def project_role_issue_lock_key(actor_id: UUID, project_id: UUID, role: str) -> int:
    encoded = json.dumps(
        [
            "workstream.project_role_grant.issue.v1",
            str(actor_id),
            str(project_id),
            role,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big", signed=True)


def _facts(grant: ProjectRoleGrant) -> dict[str, object]:
    return {
        "status": grant.status,
        "role": grant.role,
        "scope_type": "project",
        "scope_id": grant.project_id,
        "effective": grant.status == "active",
    }


def _response(grant: ProjectRoleGrant) -> ProjectRoleGrantMutationResponse:
    return ProjectRoleGrantMutationResponse(
        id=grant.id,
        qualification_snapshot_id=grant.qualification_snapshot_id,
        project_id=UUID(grant.project_id),
        actor_profile_id=UUID(grant.actor_profile_id),
        role=ProjectRole(grant.role),
        status=grant.status,
        version=grant.version,
    )


class ProjectRoleGrantMutationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.repository = AdminAuthorizationRepository(session)
        self._mutation = AuthorityMutationService(session)
        self._audit = AuditService(session)

    async def reserve(
        self,
        *,
        key: UUID,
        actor_profile_id: UUID,
        request: ProjectRoleGrantIssueRequest | ProjectRoleGrantRevokeRequest,
    ) -> AuthorityReservationResult:
        return await self._mutation.reserve(
            idempotency_key=key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
        )

    async def record_mismatch(
        self,
        *,
        actor_profile_id: UUID,
        request: ProjectRoleGrantIssueRequest | ProjectRoleGrantRevokeRequest,
        decision: AuthorizationDecision,
    ) -> None:
        await self._mutation.record_mismatch_denial(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
            context=AuthorityMismatchContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=decision.matched_grant_id,
            ),
        )

    async def record_conflict(
        self,
        *,
        actor_profile_id: UUID,
        project_id: UUID,
        grant_id: UUID,
        decision: AuthorizationDecision,
        code: str,
        action_id: ActionId,
    ) -> None:
        event_id = uuid4()
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=event_id,
                event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
                entity_type="authorization_decision",
                entity_id=str(event_id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
                action_id=action_id,
                project_id=str(project_id),
                resource_type="project_role_grant",
                resource_id=str(grant_id),
                reason="authorization_evaluation",
                denial_code=code,
                after_facts={"allowed": False},
            )
        )

    async def complete_issue(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: ProjectRoleGrantIssueRequest,
        decision: AuthorizationDecision,
        resource: ProjectRoleGrantIssueResourceContext,
        actor_profile_id: UUID,
        reason: str,
    ) -> ProjectRoleGrantMutationResponse:
        if (
            request.reason_digest != derive_reason_digest(reason)
            or not _issue_decision_matches(decision, request, resource)
        ):
            raise TypeError("project-role issue requires exact matched authority")
        duplicate = await self.repository.find_active_project_role(
            project_id=request.project_id,
            actor_profile_id=request.target_actor_id,
            role=request.role.value,
        )
        if duplicate is not None:
            raise ProjectRoleGrantConflict("project_role_grant_exists", duplicate.id)
        evidence = request.qualification
        snapshot = await self.repository.add_project_role_snapshot(
            ProjectRoleQualificationSnapshot(
                id=uuid4(),
                project_id=str(request.project_id),
                actor_profile_id=str(request.target_actor_id),
                requested_role=request.role.value,
                skills_snapshot=evidence.skills_snapshot.model_dump(mode="json"),
                reputation_snapshot=evidence.reputation_snapshot.model_dump(mode="json"),
                prior_project_work_refs=[str(value) for value in evidence.prior_project_work_refs],
                external_expertise_refs=list(evidence.external_expertise_refs),
                captured_by_actor_profile_id=str(actor_profile_id),
                captured_by_admin_role_grant_id=decision.matched_grant_id,
            )
        )
        try:
            grant = await self.repository.add_project_role_grant(
                ProjectRoleGrant(
                    id=uuid4(),
                    project_id=str(request.project_id),
                    actor_profile_id=str(request.target_actor_id),
                    role=request.role.value,
                    status="active",
                    version=1,
                    grant_method="manual",
                    qualification_snapshot_id=snapshot.id,
                    granted_by_actor_profile_id=str(actor_profile_id),
                    granted_by_admin_role_grant_id=decision.matched_grant_id,
                    grant_reason=reason,
                )
            )
        except IntegrityError as exc:
            if (
                integrity_constraint_name(exc)
                == "uq_project_role_grants_active_exact_role"
            ):
                raise ProjectRoleGrantConflict("project_role_grant_exists", None) from exc
            raise
        common = dict(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request_id=decision.request_id,
            correlation_id=decision.correlation_id,
            target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            target_actor_ref=str(request.target_actor_id),
            matched_grant_id=str(decision.matched_grant_id),
            permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
            project_id=str(request.project_id),
            idempotency_reference=claim.record_id,
        )
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=AuthorityResponseReference(
                resource_type=AuthorityResourceType.PROJECT_ROLE_GRANT,
                resource_id=grant.id,
                version=1,
                http_status=201,
            ),
            success=(
                AuthorityAuditEventInput(
                    event_id=uuid4(),
                    event_type=AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED,
                    entity_type="qualification_snapshot",
                    entity_id=str(snapshot.id),
                    resource_type="qualification_snapshot",
                    resource_id=str(snapshot.id),
                    target_ref_kind="qualification_snapshot",
                    target_ref_id=str(snapshot.id),
                    reason="qualification_evidence_captured",
                    after_facts={"status": "captured"},
                    **common,
                ),
                AuthorityAuditEventInput(
                    event_id=uuid4(),
                    event_type=AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
                    entity_type="project_role_grant",
                    entity_id=str(grant.id),
                    resource_type="project_role_grant",
                    resource_id=str(grant.id),
                    target_ref_kind="project_role_grant",
                    target_ref_id=str(grant.id),
                    reason="authority_assignment",
                    after_facts=_facts(grant),
                    **common,
                ),
            ),
            invalidation=None,
        )
        return _response(grant)

    async def complete_revoke(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: ProjectRoleGrantRevokeRequest,
        decision: AuthorizationDecision,
        resource: ProjectRoleGrantRevokeResourceContext,
        actor_profile_id: UUID,
        reason: str,
        grant: ProjectRoleGrant,
    ) -> ProjectRoleGrantMutationResponse:
        if (
            request.reason_digest != derive_reason_digest(reason)
            or not _revoke_decision_matches(decision, request, grant, resource)
        ):
            raise TypeError("project-role revoke requires exact matched authority")
        if grant.status != "active":
            raise ProjectRoleGrantConflict("project_role_grant_already_revoked", grant.id)
        before = _facts(grant)
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = str(actor_profile_id)
        grant.revoked_by_admin_role_grant_id = decision.matched_grant_id
        grant.revoked_reason = reason
        grant.revoked_at = func.clock_timestamp()
        await self._session.flush()
        await self._session.refresh(grant)
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=AuthorityResponseReference(
                resource_type=AuthorityResourceType.PROJECT_ROLE_GRANT,
                resource_id=grant.id,
                version=2,
                http_status=200,
            ),
            success=AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED,
                entity_type="project_role_grant",
                entity_id=str(grant.id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=grant.actor_profile_id,
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
                project_id=grant.project_id,
                resource_type="project_role_grant",
                resource_id=str(grant.id),
                target_ref_kind="project_role_grant",
                target_ref_id=str(grant.id),
                reason="authority_revocation",
                idempotency_reference=claim.record_id,
                before_facts=before,
                after_facts=_facts(grant),
            ),
            invalidation=AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_ref_kind=AuthorityResourceType.PROJECT_ROLE_GRANT,
                target_ref_id=grant.id,
                project_role=ProjectRole(grant.role),
                future_obligation={
                    ProjectRole.SUBMITTER: "auth13_assignment",
                    ProjectRole.REVIEWER: "rev_reviewer_obligation",
                    ProjectRole.ADJUDICATOR: "none",
                }[ProjectRole(grant.role)],
            ),
        )
        return _response(grant)


def _issue_decision_matches(
    decision: AuthorizationDecision,
    request: ProjectRoleGrantIssueRequest,
    resource: ProjectRoleGrantIssueResourceContext,
) -> bool:
    return (
        decision.allowed
        and decision.revalidated
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.action_id is ActionId.PROJECT_ROLE_GRANT_ISSUE
        and decision.permission_id is PermissionId.PROJECT_ROLE_GRANT_MANAGE
        and resource.resource_id == request.project_id
        and resource.scope_project_id == request.project_id
        and resource.target_actor_profile_id == request.target_actor_id
        and resource.role is request.role
        and resource.target_eligible
        and not resource.active_exact_role_exists
        and decision.resource_type == resource.resource_type
        and decision.resource_id == resource.resource_id
        and decision.resource_context_digest == authorization_resource_digest(resource)
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id == request.project_id
    )


def _revoke_decision_matches(
    decision: AuthorizationDecision,
    request: ProjectRoleGrantRevokeRequest,
    grant: ProjectRoleGrant,
    resource: ProjectRoleGrantRevokeResourceContext,
) -> bool:
    return (
        decision.allowed
        and decision.revalidated
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.action_id is ActionId.PROJECT_ROLE_GRANT_REVOKE
        and decision.permission_id is PermissionId.PROJECT_ROLE_GRANT_MANAGE
        and resource.resource_id == request.grant_id == grant.id
        and resource.scope_project_id == request.project_id == UUID(grant.project_id)
        and resource.actor_profile_id == UUID(grant.actor_profile_id)
        and resource.role.value == grant.role
        and resource.status == grant.status
        and resource.version == grant.version
        and decision.resource_type == resource.resource_type
        and decision.resource_id == resource.resource_id
        and decision.resource_context_digest == authorization_resource_digest(resource)
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id == request.project_id
    )
