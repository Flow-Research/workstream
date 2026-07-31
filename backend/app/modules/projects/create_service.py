"""Authorization-aware orchestration for project creation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectCreateResourceContext,
)
from app.modules.projects.create_repository import ProjectCreateRepository
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectResponse
from app.modules.projects.service import ProjectServiceError


class ProjectCreateIdempotencyConflict(ProjectServiceError):
    """One project-create replay key was reused with incompatible state."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class ProjectCreateOutcome:
    """Route-owned transaction outcome for one project-create request."""

    response: ProjectResponse
    replayed: bool


class ProjectCreateService:
    """Create one project through the exact prepared-authorization protocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind all project-create persistence to one caller-owned transaction."""
        self._projects = ProjectRepository(session)
        self._reservations = ProjectCreateRepository(session)

    async def create(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        idempotency_key: UUID,
        payload: ProjectCreate,
    ) -> ProjectCreateOutcome:
        """Create or exactly replay one authorized draft project shell."""
        actor_profile_id = resolved.profile.id
        identity_link_id = resolved.identity_link.id
        request_digest = canonical_json_hash(
            {
                "domain": "workstream.project_create.idempotency.v1",
                "action_id": ActionId.PROJECT_CREATE.value,
                "route": "POST /api/v1/projects",
                "actor_profile_id": actor_profile_id,
                "identity_link_id": identity_link_id,
                "idempotency_key": str(idempotency_key),
                "body": payload.model_dump(mode="json", exclude_none=True),
            }
        )
        disposition, reservation = await self._reservations.reserve(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        if disposition == "mismatch":
            raise ProjectCreateIdempotencyConflict("idempotency_mismatch")
        if disposition == "pending":
            raise ProjectCreateIdempotencyConflict("idempotency_pending")
        if disposition == "replayed":
            existing = await self._projects.get_project(reservation.project_id)
            if existing is None:
                raise RuntimeError("committed project replay lost its project")
            return ProjectCreateOutcome(
                response=ProjectResponse.model_validate(existing), replayed=True
            )
        prepared_input = PreparedAuthorizationInput(
            idempotency_key=idempotency_key,
            request_value={
                "action_id": ActionId.PROJECT_CREATE.value,
                "route": "POST /api/v1/projects",
                "actor_profile_id": actor_profile_id,
                "identity_link_id": identity_link_id,
                "idempotency_key": str(idempotency_key),
                "request_digest": request_digest,
                "operation_id": str(reservation.operation_id),
                "project_id": reservation.project_id,
                "operation_generation": reservation.operation_generation,
                "body": payload.model_dump(mode="json", exclude_none=True),
            },
        )
        final_resource = ProjectCreateResourceContext(
            resource_type="project_create",
            resource_id=reservation.operation_id,
            requested_project_id=UUID(reservation.project_id),
            operation_generation=reservation.operation_generation,
        )
        try:
            handle = await prepared.prepare(
                ActionId.PROJECT_CREATE,
                prepared_input,
                PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
            )
        except PreparedAuthorizationUnsupported as exc:
            await prepared.deny_unsupported(
                ActionId.PROJECT_CREATE, prepared_input, final_resource, exc
            )
        decision = await prepared.consume(
            handle,
            ActionId.PROJECT_CREATE,
            prepared_input,
            final_resource,
        )
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id is not None
        ):
            raise RuntimeError("project creation unexpectedly lacked system authority")
        project = Project(
            id=reservation.project_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            status="draft",
            created_by_actor_profile_id=actor_profile_id,
            created_via_identity_link_id=identity_link_id,
            created_by_admin_role_grant_id=decision.matched_grant_id,
            creation_scope_type="system",
            creation_action_id=ActionId.PROJECT_CREATE.value,
            authorization_decision_event_id=str(decision.decision_id),
        )
        project = await self._projects.add_project(project)
        await self._reservations.complete(reservation)
        return ProjectCreateOutcome(
            response=ProjectResponse.model_validate(project), replayed=False
        )
