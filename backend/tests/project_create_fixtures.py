"""Test-only construction of historical and currently attributed projects."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.core.hashing import canonical_json_hash
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
from app.modules.authorization.runtime import (
    ProjectCreateResourceContext,
    authorization_resource_digest,
)
from app.modules.projects.models import Project, ProjectCreateIdempotencyRecord


async def grant_system_project_manager(
    session: AsyncSession,
    *,
    issuer: str,
    subject: str,
) -> tuple[ActorIdentityLink, AdminRoleGrant]:
    """Grant the admitted test actor the authority required by project.create."""
    link = await session.scalar(
        select(ActorIdentityLink).where(
            ActorIdentityLink.issuer == issuer,
            ActorIdentityLink.subject == subject,
        )
    )
    if link is None:
        raise RuntimeError("project manager fixture requires an admitted actor")
    control = await session.get(AuthorityControl, 1, with_for_update=True)
    if control is None:
        raise RuntimeError("project manager fixture requires authority control")
    bootstrap = (
        await session.get(AdminRoleGrant, control.bootstrap_grant_id)
        if control.bootstrap_grant_id is not None
        else None
    )
    if bootstrap is None:
        bootstrap_actor = ActorProfile(
            id=str(uuid4()),
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            service_identity=None,
            created_by="test",
        )
        session.add(bootstrap_actor)
        await session.flush()
        session.add(
            ActorIdentityLink(
                id=str(uuid4()),
                actor_profile_id=bootstrap_actor.id,
                issuer="https://project-fixture-bootstrap.test",
                subject=f"project-fixture-bootstrap-{bootstrap_actor.id}",
                subject_kind="human",
                status="active",
                linked_by="test",
                last_verified_at=datetime.now(UTC),
            )
        )
        await session.flush()
        bootstrap = AdminRoleGrant(
            id=uuid4(),
            target_actor_profile_id=bootstrap_actor.id,
            role="access_administrator",
            scope_type="system",
            scope_project_id=None,
            status="active",
            version=1,
            granted_by_system_principal="workstream:system:bootstrap",
            grant_reason="project manager fixture bootstrap",
        )
        session.add(bootstrap)
        control.bootstrap_completed = True
        control.bootstrap_grant_id = bootstrap.id
        control.version = max(control.version, 1)
        await session.flush()
    grant = await session.scalar(
        select(AdminRoleGrant).where(
            AdminRoleGrant.target_actor_profile_id == link.actor_profile_id,
            AdminRoleGrant.role == "project_manager",
            AdminRoleGrant.scope_type == "system",
            AdminRoleGrant.status == "active",
        )
    )
    if grant is None:
        grant = AdminRoleGrant(
            id=uuid4(),
            target_actor_profile_id=link.actor_profile_id,
            role="project_manager",
            scope_type="system",
            scope_project_id=None,
            status="active",
            version=1,
            granted_by_actor_profile_id=bootstrap.target_actor_profile_id,
            granted_by_admin_role_grant_id=bootstrap.id,
            grant_reason="project manager fixture authority",
        )
        session.add(grant)
        await session.flush()
    return link, grant


async def seed_historical_project(
    session: AsyncSession,
    *,
    project_id: str,
    name: str,
    slug: str,
    status: str = "draft",
) -> None:
    """Stage a pre-0044 project without manufacturing current authority evidence."""
    await insert_historical_project(
        session,
        project_id=project_id,
        name=name,
        slug=slug,
        status=status,
    )


async def insert_historical_project(
    connection: AsyncConnection | AsyncSession,
    *,
    project_id: str,
    name: str,
    slug: str,
    status: str = "draft",
) -> None:
    """Insert one pre-0044 project in the caller-owned transaction."""
    has_cutover = await connection.scalar(
        text("select to_regclass('public.project_create_idempotency_records') is not null")
    )
    if has_cutover:
        # These shared fixtures model projects that predate the clean-cut
        # project.create boundary. Disable only the 0044 custody trigger for the
        # statement so no deferred event is queued, then restore it immediately.
        await connection.execute(
            text("alter table projects disable trigger project_creation_custody")
        )
    try:
        await connection.execute(
            text(
                "insert into projects (id, name, slug, status) "
                "values (:id, :name, :slug, :status)"
            ),
            {"id": project_id, "name": name, "slug": slug, "status": status},
        )
    finally:
        if has_cutover:
            await connection.execute(
                text("alter table projects enable trigger project_creation_custody")
            )


async def seed_authorized_project(
    session: AsyncSession,
    *,
    project_id: str,
    name: str,
    slug: str,
    status: str = "draft",
) -> None:
    """Stage current project-create custody for tests of the 0044 boundary itself."""
    project_uuid = UUID(project_id)
    actor_id = str(uuid4())
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=actor_id,
        issuer="https://project-fixture.test",
        subject=f"project-fixture-{actor_id}",
        subject_kind="human",
        status="active",
        linked_by="test",
        last_verified_at=datetime.now(UTC),
    )
    session.add(
        ActorProfile(
            id=actor_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            service_identity=None,
            created_by="test",
        )
    )
    await session.flush()
    session.add(link)
    await session.flush()
    link, grant = await grant_system_project_manager(
        session,
        issuer=link.issuer,
        subject=link.subject,
    )
    operation_id = uuid4()
    decision_id = uuid4()
    resource = ProjectCreateResourceContext(
        resource_type="project_create",
        resource_id=operation_id,
        requested_project_id=project_uuid,
        operation_generation=1,
    )
    await AuditService(session).add_authority_event(
        AuthorityAuditEventInput(
            event_id=decision_id,
            event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            entity_type="authorization_decision",
            entity_id=str(decision_id),
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=link.actor_profile_id,
            request_id=uuid4(),
            correlation_id=uuid4(),
            matched_grant_id=str(grant.id),
            permission_id=PermissionId.PROJECT_CREATE,
            action_id=ActionId.PROJECT_CREATE,
            resource_type="project_create_operation",
            resource_id=str(operation_id),
            target_ref_kind="project",
            target_ref_id=project_id,
            reason="authorization_evaluation",
            after_facts={
                "allowed": True,
                "resource_context_digest": authorization_resource_digest(resource),
            },
        )
    )
    reservation = ProjectCreateIdempotencyRecord(
        id=uuid4(),
        actor_profile_id=link.actor_profile_id,
        identity_link_id=link.id,
        action_id=ActionId.PROJECT_CREATE.value,
        idempotency_key=uuid4(),
        request_digest=canonical_json_hash(
            {"domain": "workstream.test.project_create", "project_id": project_id}
        ),
        operation_id=operation_id,
        project_id=project_id,
        operation_generation=1,
        status="pending",
    )
    session.add(reservation)
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name=name,
            slug=slug,
            status=status,
            created_by_actor_profile_id=link.actor_profile_id,
            created_via_identity_link_id=link.id,
            created_by_admin_role_grant_id=grant.id,
            creation_scope_type="system",
            creation_action_id=ActionId.PROJECT_CREATE.value,
            authorization_decision_event_id=str(decision_id),
        )
    )
    reservation.status = "committed"
    reservation.committed_at = datetime.now(UTC)
    await session.flush()
