"""Privacy-safe orchestration for project-role authorization reads."""

from __future__ import annotations

from uuid import UUID

from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import ActorAuthorizationContextResponse
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.authorization.kernel import (
    AuthorizationService,
    project_action_available_for_status,
)
from app.modules.authorization.models import (
    ProjectRoleGrant,
    ProjectRoleQualificationSnapshot,
)
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec,
    InvalidPaginationCursor,
    authorization_read_query_digest,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorAuthorizationContextResourceContext,
    ProjectContributorCandidateCollectionResourceContext,
    ProjectRoleGrantCollectionResourceContext,
    ProjectRoleGrantReadResourceContext,
)
from app.modules.authorization.schemas import (
    AdminRole,
    ContributorCandidateListResponse,
    ContributorCandidateRead,
    ProjectRole,
    ProjectRoleGrantListResponse,
    ProjectRoleGrantRead,
    ProjectRoleQualificationSnapshotRead,
    QualificationAvailabilitySnapshot,
)
from app.modules.projects.models import Project
from app.modules.authorization.policy import permissions_for


_PROJECT_CONTEXT_ACTIONS = (
    ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
    ActionId.PROJECT_ROLE_GRANT_LIST,
    ActionId.PROJECT_ROLE_GRANT_READ,
    ActionId.PROJECT_ROLE_GRANT_ISSUE,
    ActionId.PROJECT_ROLE_GRANT_REVOKE,
    ActionId.PROJECT_READ,
    ActionId.PROJECT_SETUP_RUN_READ,
    ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
    ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
    ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
    ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
    ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
    ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
    ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
    ActionId.PROJECT_ACTIVE_GUIDE_READ,
)


class ProjectRoleReadResourceNotFound(LookupError):
    """One concealed absence for project or project-role grant reads."""


class ActorAuthorizationContextReadService:
    """Build one bounded self authority projection from canonical local grants."""

    def __init__(
        self,
        authorization: AuthorizationService,
        grants: AdminAuthorizationRepository,
    ) -> None:
        self._authorization = authorization
        self._grants = grants

    async def read(
        self,
        *,
        resolved: ResolvedActor,
        project: Project | None,
        project_selector_id: UUID,
    ) -> ActorAuthorizationContextResponse:
        """Authorize self access and derive effective exact-project actions."""
        actor_profile_id = UUID(resolved.profile.id)
        project_id = UUID(project.id) if project is not None else project_selector_id
        await self._authorization.require(
            ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
            ActorAuthorizationContextResourceContext(
                resource_type="actor_authorization_context",
                resource_id=actor_profile_id,
                scope_project_id=project_id,
                project_exists=project is not None,
                project_status=project.status if project is not None else None,
            ),
        )
        if project is None:
            raise RuntimeError("missing project authorization unexpectedly allowed")
        admin_roles = await self._grants.effective_admin_roles_for_project(
            project_id=project_id,
            actor_profile_id=actor_profile_id,
        )
        project_roles = await self._grants.active_project_roles_for_actor(
            project_id=project_id,
            actor_profile_id=actor_profile_id,
        )
        eligible_admin_roles = tuple(
            role_name
            for role_name in admin_roles
            if any(
                ACTION_BY_ID[action_id].availability is ActionAvailability.ACTIVE
                and ACTION_BY_ID[action_id].permission_id
                in permissions_for(AdminRole(role_name))
                for action_id in _PROJECT_CONTEXT_ACTIONS
            )
        )
        admin_permissions = {
            permission
            for role_name in eligible_admin_roles
            for permission in permissions_for(AdminRole(role_name))
        }
        effective_actions = {
            action_id
            for action_id in _PROJECT_CONTEXT_ACTIONS
            if ACTION_BY_ID[action_id].availability is ActionAvailability.ACTIVE
            and ACTION_BY_ID[action_id].permission_id in admin_permissions
            and project_action_available_for_status(action_id, project.status)
        }
        if project_roles:
            effective_actions.add(ActionId.PROJECT_READ)
        return ActorAuthorizationContextResponse(
            actor_profile_id=actor_profile_id,
            status=resolved.profile.status,
            project_id=project_id,
            admin_roles=eligible_admin_roles,
            project_roles=project_roles,
            effective_action_ids=tuple(sorted(effective_actions, key=str)),
        )


class ProjectRoleReadService:
    """Authorize before decoding cursors and querying private read rows."""

    def __init__(
        self,
        authorization: AuthorizationService,
        actors: ActorRepository,
        grants: AdminAuthorizationRepository,
        cursor_codec: AuthorizationReadCursorCodec,
    ) -> None:
        self._authorization = authorization
        self._actors = actors
        self._grants = grants
        self._cursor_codec = cursor_codec

    async def list_contributor_candidates(
        self,
        *,
        project: Project,
        caller_actor_profile_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> ContributorCandidateListResponse:
        """Return one authorized, count-free page of eligible humans."""
        project_id = UUID(project.id)
        await self._authorization.require(
            ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
            ProjectContributorCandidateCollectionResourceContext(
                resource_type="project_contributor_candidate_collection",
                resource_id=project_id,
                scope_project_id=project_id,
                project_status=project.status,
            ),
        )
        digest = authorization_read_query_digest(
            action_id=ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
            project_id=project_id,
            limit=limit,
        )
        boundary = self._cursor_codec.decode(cursor, query_digest=digest) if cursor else None
        rows = await self._actors.list_contributor_candidates(
            caller_actor_profile_id=caller_actor_profile_id,
            cursor=boundary,
            limit=limit,
        )
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1]
            next_cursor = self._cursor_codec.encode(
                query_digest=digest,
                timestamp=last.created_at,
                resource_id=UUID(last.id),
            )
        return ContributorCandidateListResponse(
            items=[
                ContributorCandidateRead(
                    actor_profile_id=UUID(row.id),
                    display_name=row.display_name,
                )
                for row in visible
            ],
            next_cursor=next_cursor,
        )

    async def list_project_role_grants(
        self,
        *,
        project: Project,
        status: str | None,
        role: ProjectRole | None,
        limit: int,
        cursor: str | None,
    ) -> ProjectRoleGrantListResponse:
        """Return one authorized page of immutable project grant history."""
        project_id = UUID(project.id)
        await self._authorization.require(
            ActionId.PROJECT_ROLE_GRANT_LIST,
            ProjectRoleGrantCollectionResourceContext(
                resource_type="project_role_grant_collection",
                resource_id=project_id,
                scope_project_id=project_id,
                project_status=project.status,
            ),
        )
        digest = authorization_read_query_digest(
            action_id=ActionId.PROJECT_ROLE_GRANT_LIST,
            project_id=project_id,
            status=status,
            role=role,
            limit=limit,
        )
        boundary = self._cursor_codec.decode(cursor, query_digest=digest) if cursor else None
        rows = await self._grants.list_project_role_grants(
            project_id=project_id,
            status=status,
            role=role.value if role is not None else None,
            cursor=boundary,
            limit=limit,
        )
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1][0]
            next_cursor = self._cursor_codec.encode(
                query_digest=digest,
                timestamp=last.granted_at,
                resource_id=last.id,
            )
        return ProjectRoleGrantListResponse(
            items=[_grant_read(grant, snapshot) for grant, snapshot in visible],
            next_cursor=next_cursor,
        )

    async def read_project_role_grant(
        self,
        *,
        project: Project,
        grant_id: UUID,
    ) -> ProjectRoleGrantRead:
        """Return one authorized grant only when it belongs to the path project."""
        project_id = UUID(project.id)
        await self._authorization.require(
            ActionId.PROJECT_ROLE_GRANT_READ,
            ProjectRoleGrantReadResourceContext(
                resource_type="project_role_grant",
                resource_id=grant_id,
                scope_project_id=project_id,
                project_status=project.status,
            ),
        )
        row = await self._grants.get_project_role_grant(
            project_id=project_id,
            grant_id=grant_id,
        )
        if row is None:
            raise ProjectRoleReadResourceNotFound("project role grant not found")
        return _grant_read(*row)


def _grant_read(
    grant: ProjectRoleGrant,
    snapshot: ProjectRoleQualificationSnapshot,
) -> ProjectRoleGrantRead:
    qualification = ProjectRoleQualificationSnapshotRead(
        id=snapshot.id,
        requested_role=ProjectRole(snapshot.requested_role),
        skills_snapshot=QualificationAvailabilitySnapshot.model_validate(
            snapshot.skills_snapshot,
            strict=False,
        ),
        reputation_snapshot=QualificationAvailabilitySnapshot.model_validate(
            snapshot.reputation_snapshot,
            strict=False,
        ),
        prior_project_work_refs=[UUID(value) for value in snapshot.prior_project_work_refs],
        external_expertise_refs=list(snapshot.external_expertise_refs),
        captured_by_actor_profile_id=UUID(snapshot.captured_by_actor_profile_id),
        captured_by_admin_role_grant_id=snapshot.captured_by_admin_role_grant_id,
        captured_at=snapshot.captured_at,
    )
    return ProjectRoleGrantRead(
        id=grant.id,
        project_id=UUID(grant.project_id),
        actor_profile_id=UUID(grant.actor_profile_id),
        role=ProjectRole(grant.role),
        status=grant.status,
        version=grant.version,
        grant_method=grant.grant_method,
        qualification_snapshot=qualification,
        granted_by_actor_profile_id=UUID(grant.granted_by_actor_profile_id),
        granted_by_admin_role_grant_id=grant.granted_by_admin_role_grant_id,
        granted_at=grant.granted_at,
        grant_reason=grant.grant_reason,
        revoked_by_actor_profile_id=(
            UUID(grant.revoked_by_actor_profile_id)
            if grant.revoked_by_actor_profile_id is not None
            else None
        ),
        revoked_at=grant.revoked_at,
        revoked_reason=grant.revoked_reason,
    )


__all__ = [
    "ActorAuthorizationContextReadService",
    "InvalidPaginationCursor",
    "ProjectRoleReadResourceNotFound",
    "ProjectRoleReadService",
]
