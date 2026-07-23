"""Prepared, idempotent project-role grant mutations."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.models import ProjectRoleGrant, ProjectRoleQualificationSnapshot
from app.modules.authorization.project_role_schemas import ProjectRoleGrantMutationResponse
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import AuthorizationDecision
from app.modules.authorization.schemas import (
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
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
    pass


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

    async def complete_issue(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: ProjectRoleGrantIssueRequest,
        decision: AuthorizationDecision,
        actor_profile_id: UUID,
        reason: str,
    ) -> ProjectRoleGrantMutationResponse:
        if (
            request.reason_digest != derive_reason_digest(reason)
            or decision.matched_grant_id is None
        ):
            raise TypeError("project-role issue requires exact matched authority")
        await self.repository.take_project_role_issue_lock(
            project_role_issue_lock_key(
                request.target_actor_id, request.project_id, request.role.value
            )
        )
        if (
            await self.repository.find_active_project_role(
                project_id=request.project_id,
                actor_profile_id=request.target_actor_id,
                role=request.role.value,
            )
            is not None
        ):
            raise ProjectRoleGrantConflict("project_role_grant_exists")
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
        actor_profile_id: UUID,
        reason: str,
        grant: ProjectRoleGrant,
    ) -> ProjectRoleGrantMutationResponse:
        if (
            request.reason_digest != derive_reason_digest(reason)
            or decision.matched_grant_id is None
        ):
            raise TypeError("project-role revoke requires exact matched authority")
        if grant.status != "active":
            raise ProjectRoleGrantConflict("project_role_grant_already_revoked")
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
            ),
        )
        return _response(grant)
