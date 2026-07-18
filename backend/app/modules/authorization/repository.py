"""Caller-transaction persistence for authority mutation idempotency."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.models import (
    AdminRoleGrant,
    AuthorityControl,
    AuthorityIdempotencyRecord,
)
from app.modules.authorization.policy import permissions_for
from app.modules.authorization.schemas import (
    AdminRole,
    AdminScope,
    AuthorityClaimHandle,
    AuthorityOperation,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    ClaimedReservation,
    InvalidAuthorityClaimError,
    MismatchedReservation,
    PendingAuthorityReservationError,
    ReplayedReservation,
)
from app.modules.audit.schemas import ActorReferenceKind
from app.modules.projects.repository import ProjectRepository


class AdminAuthorizationRepository:
    """Canonical administrative grant and guard queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)

    async def lock_control(self) -> AuthorityControl:
        """Lock the irreversible singleton before any administrative mutation."""
        control = await self._session.scalar(
            select(AuthorityControl).where(AuthorityControl.id == 1).with_for_update()
        )
        if control is None:
            raise RuntimeError("authority control is missing")
        return control

    async def lock_request_actor(
        self,
        identity_link_id: UUID,
        actor_profile_id: UUID,
    ) -> tuple[ActorIdentityLink, ActorProfile] | None:
        """Lock and validate the request actor profile before its exact link."""
        profile = await self._session.scalar(
            select(ActorProfile)
            .where(ActorProfile.id == str(actor_profile_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if profile is None:
            return None
        link = await self._session.scalar(
            select(ActorIdentityLink)
            .where(ActorIdentityLink.id == str(identity_link_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if link is None or link.actor_profile_id != str(actor_profile_id):
            return None
        return link, profile

    async def find_effective_grant(
        self,
        actor_profile_id: UUID,
        permission_id: PermissionId,
        *,
        scope_project_id: UUID | None,
        system_scope_only: bool = False,
        for_update: bool = False,
    ) -> AdminRoleGrant | None:
        """Load one deterministic effective candidate covering the exact scope."""
        roles = [role.value for role in AdminRole if permission_id in permissions_for(role)]
        scope_guard = AdminRoleGrant.scope_type == "system"
        if not system_scope_only and scope_project_id is not None:
            scope_guard = or_(
                scope_guard,
                and_(
                    AdminRoleGrant.scope_type == "project",
                    AdminRoleGrant.scope_project_id == str(scope_project_id),
                ),
            )
        active_link = exists(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == ActorProfile.id,
                ActorIdentityLink.status == "active",
            )
        )
        role_order = case(
            {role.value: index for index, role in enumerate(AdminRole)},
            value=AdminRoleGrant.role,
        )
        query = (
            select(AdminRoleGrant)
            .join(ActorProfile, ActorProfile.id == AdminRoleGrant.target_actor_profile_id)
            .where(
                AdminRoleGrant.target_actor_profile_id == str(actor_profile_id),
                AdminRoleGrant.status == "active",
                AdminRoleGrant.role.in_(roles),
                scope_guard,
                ActorProfile.actor_kind == "human",
                ActorProfile.status == "active",
                active_link,
            )
            .order_by(role_order, AdminRoleGrant.granted_at, AdminRoleGrant.id)
            .limit(1)
        )
        if for_update:
            query = query.with_for_update(of=AdminRoleGrant)
        return await self._session.scalar(query)

    async def get_eligible_human(
        self,
        actor_profile_id: UUID,
        *,
        for_update: bool = False,
    ) -> ActorProfile | None:
        """Load an active human with at least one active identity link."""
        active_link = exists(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == ActorProfile.id,
                ActorIdentityLink.status == "active",
            )
        )
        query = select(ActorProfile).where(
            ActorProfile.id == str(actor_profile_id),
            ActorProfile.actor_kind == "human",
            ActorProfile.status == "active",
            active_link,
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def lock_eligible_human(
        self,
        actor_profile_id: UUID,
    ) -> tuple[ActorIdentityLink, ActorProfile] | None:
        """Lock one active human profile and then its deterministic active link."""
        profile = await self._session.scalar(
            select(ActorProfile)
            .where(
                ActorProfile.id == str(actor_profile_id),
                ActorProfile.actor_kind == "human",
                ActorProfile.status == "active",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if profile is None:
            return None
        link = await self._session.scalar(
            select(ActorIdentityLink)
            .where(
                ActorIdentityLink.actor_profile_id == str(actor_profile_id),
                ActorIdentityLink.status == "active",
            )
            .order_by(ActorIdentityLink.id)
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if link is None:
            return None
        return link, profile

    async def actor_exists(self, actor_profile_id: UUID) -> bool:
        """Return whether one canonical actor profile exists."""
        return (
            await self._session.scalar(
                select(ActorProfile.id).where(ActorProfile.id == str(actor_profile_id))
            )
            is not None
        )

    async def has_effective_permission_any_scope(
        self,
        actor_profile_id: UUID,
        permission_id: PermissionId,
    ) -> bool:
        """Detect a permission candidate whose project scope does not cover a target."""
        roles = [role.value for role in AdminRole if permission_id in permissions_for(role)]
        active_link = exists(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == ActorProfile.id,
                ActorIdentityLink.status == "active",
            )
        )
        return (
            await self._session.scalar(
                select(AdminRoleGrant.id)
                .join(ActorProfile, ActorProfile.id == AdminRoleGrant.target_actor_profile_id)
                .where(
                    AdminRoleGrant.target_actor_profile_id == str(actor_profile_id),
                    AdminRoleGrant.status == "active",
                    AdminRoleGrant.role.in_(roles),
                    ActorProfile.actor_kind == "human",
                    ActorProfile.status == "active",
                    active_link,
                )
                .limit(1)
            )
            is not None
        )

    async def project_exists(self, project_id: UUID, *, for_update: bool = False) -> bool:
        """Resolve an exact project from Workstream-owned records."""
        return (
            await self._projects.get_project(str(project_id), for_update=for_update)
            is not None
        )

    async def get_grant(
        self,
        grant_id: UUID,
        *,
        for_update: bool = False,
    ) -> AdminRoleGrant | None:
        """Load one administrative grant by immutable identifier."""
        query = select(AdminRoleGrant).where(AdminRoleGrant.id == grant_id)
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def find_active_duplicate(
        self,
        *,
        target_actor_profile_id: UUID,
        role: AdminRole,
        scope_type: AdminScope,
        scope_project_id: UUID | None,
    ) -> AdminRoleGrant | None:
        """Load an already-active grant with the exact target/role/scope."""
        return await self._session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == str(target_actor_profile_id),
                AdminRoleGrant.role == role.value,
                AdminRoleGrant.scope_type == scope_type.value,
                AdminRoleGrant.scope_project_id
                == (str(scope_project_id) if scope_project_id else None),
                AdminRoleGrant.status == "active",
            )
        )

    async def count_effective_access_administrators(self) -> int:
        """Count authenticatable effective system Access Administrators."""
        active_link = exists(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == ActorProfile.id,
                ActorIdentityLink.status == "active",
            )
        )
        return int(
            await self._session.scalar(
                select(func.count(AdminRoleGrant.id))
                .join(ActorProfile, ActorProfile.id == AdminRoleGrant.target_actor_profile_id)
                .where(
                    AdminRoleGrant.role == AdminRole.ACCESS_ADMINISTRATOR.value,
                    AdminRoleGrant.scope_type == AdminScope.SYSTEM.value,
                    AdminRoleGrant.status == "active",
                    ActorProfile.actor_kind == "human",
                    ActorProfile.status == "active",
                    active_link,
                )
            )
            or 0
        )

    async def add_grant(self, grant: AdminRoleGrant) -> AdminRoleGrant:
        """Stage one immutable administrative grant."""
        self._session.add(grant)
        await self._session.flush()
        await self._session.refresh(grant)
        return grant

    async def list_grants(
        self,
        *,
        scope_type: AdminScope,
        scope_project_id: UUID | None,
        target_actor_profile_id: UUID | None,
        status: str,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> tuple[list[AdminRoleGrant], int]:
        """Return a scope-filtered page and total before disclosure."""
        filters = [AdminRoleGrant.scope_type == scope_type.value]
        filters.append(
            AdminRoleGrant.scope_project_id
            == (str(scope_project_id) if scope_project_id is not None else None)
        )
        if target_actor_profile_id is not None:
            filters.append(AdminRoleGrant.target_actor_profile_id == str(target_actor_profile_id))
        if status != "all":
            filters.append(AdminRoleGrant.status == status)
        total = int(
            await self._session.scalar(select(func.count(AdminRoleGrant.id)).where(*filters)) or 0
        )
        page_filters = list(filters)
        if cursor is not None:
            created_at, grant_id = cursor
            page_filters.append(
                or_(
                    AdminRoleGrant.granted_at > created_at,
                    and_(AdminRoleGrant.granted_at == created_at, AdminRoleGrant.id > grant_id),
                )
            )
        rows = list(
            (
                await self._session.scalars(
                    select(AdminRoleGrant)
                    .where(*page_filters)
                    .order_by(AdminRoleGrant.granted_at, AdminRoleGrant.id)
                    .limit(limit + 1)
                )
            ).all()
        )
        return rows, total

    async def active_roles_for_actor(self, actor_profile_id: UUID) -> tuple[str, ...]:
        """Project sorted unique active role names for self display only."""
        roles = await self._session.scalars(
            select(AdminRoleGrant.role)
            .where(
                AdminRoleGrant.target_actor_profile_id == str(actor_profile_id),
                AdminRoleGrant.status == "active",
            )
            .distinct()
            .order_by(AdminRoleGrant.role)
        )
        return tuple(roles.all())


class AuthorityIdempotencyRepository:
    """Reserve, lock, and complete records without transaction ownership."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind persistence operations to the caller-owned session."""

        self._session = session

    async def reserve(
        self,
        *,
        idempotency_key: UUID,
        actor_ref_kind: ActorReferenceKind,
        actor_ref: str,
        operation: AuthorityOperation,
        request_digest: str,
    ) -> AuthorityReservationResult:
        """Claim a new namespace or return its committed replay disposition."""
        values = {
            "id": uuid4(),
            "idempotency_key": idempotency_key,
            "actor_ref_kind": actor_ref_kind.value,
            "actor_ref": actor_ref,
            "operation": operation.value,
            "request_digest": request_digest,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(AuthorityIdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    AuthorityIdempotencyRecord.actor_ref_kind,
                    AuthorityIdempotencyRecord.actor_ref,
                    AuthorityIdempotencyRecord.operation,
                    AuthorityIdempotencyRecord.idempotency_key,
                ]
            )
            .returning(AuthorityIdempotencyRecord.id)
        )
        if record_id is not None:
            return ClaimedReservation(
                claim=AuthorityClaimHandle(
                    record_id=record_id,
                    idempotency_key=idempotency_key,
                    actor_ref_kind=actor_ref_kind,
                    actor_ref=actor_ref,
                    operation=operation,
                    request_digest=request_digest,
                )
            )

        record = await self._session.scalar(
            select(AuthorityIdempotencyRecord)
            .where(
                AuthorityIdempotencyRecord.actor_ref_kind == actor_ref_kind.value,
                AuthorityIdempotencyRecord.actor_ref == actor_ref,
                AuthorityIdempotencyRecord.operation == operation.value,
                AuthorityIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("authority reservation conflict was not visible")
        if record.request_digest != request_digest:
            return MismatchedReservation()
        if record.status == "pending":
            raise PendingAuthorityReservationError("authority reservation is pending")
        return ReplayedReservation(
            response=AuthorityResponseReference(
                resource_type=AuthorityResourceType(record.response_resource_type),
                resource_id=record.response_resource_id,
                version=record.response_resource_version,
                http_status=record.response_http_status,
            )
        )

    async def complete(
        self,
        claim: AuthorityClaimHandle,
        response: AuthorityResponseReference,
    ) -> None:
        """Atomically complete exactly the pending row owned by a claim handle."""
        result = await self._session.execute(
            update(AuthorityIdempotencyRecord)
            .where(
                AuthorityIdempotencyRecord.id == claim.record_id,
                AuthorityIdempotencyRecord.idempotency_key == claim.idempotency_key,
                AuthorityIdempotencyRecord.actor_ref_kind == claim.actor_ref_kind.value,
                AuthorityIdempotencyRecord.actor_ref == claim.actor_ref,
                AuthorityIdempotencyRecord.operation == claim.operation.value,
                AuthorityIdempotencyRecord.request_digest == claim.request_digest,
                AuthorityIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                response_resource_type=response.resource_type.value,
                response_resource_id=response.resource_id,
                response_resource_version=response.version,
                response_http_status=response.http_status,
            )
            .returning(AuthorityIdempotencyRecord.id)
        )
        if result.scalar_one_or_none() is None:
            raise InvalidAuthorityClaimError("invalid authority claim")
