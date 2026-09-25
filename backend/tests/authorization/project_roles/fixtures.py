"""Small AUTH-owned fixture facts for project-role mutation tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.schemas import (
    QualificationAvailability,
    QualificationUnavailableReason,
)
from project_create_fixtures import seed_historical_project


@pytest.fixture
def authorization_database_env(isolated_database_env: str) -> str:
    """Use the shared migrated, per-test PostgreSQL database."""
    return isolated_database_env


@pytest.fixture
async def authorization_factory(authorization_database_env: str) -> AsyncIterator:
    """Create request sessions; the shared database fixture owns reset/verification."""
    engine = create_async_engine(authorization_database_env)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class RoleMutationCase:
    caller_id: UUID = field(default_factory=new_record_id)
    caller_link_id: UUID = field(default_factory=new_record_id)
    target_id: UUID = field(default_factory=new_record_id)
    target_link_id: UUID = field(default_factory=new_record_id)
    project_id: UUID = field(default_factory=new_record_id)
    manager_grant_id: UUID = field(default_factory=new_record_id)
    bootstrap_grant_id: UUID = field(default_factory=new_record_id)
    context: HumanAuthorizationContext = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "context",
            HumanAuthorizationContext(
                actor_profile_id=self.caller_id,
                actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE,
                identity_link_id=self.caller_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=new_record_id(),
                correlation_id=new_record_id(),
            ),
        )


def project_role_qualification() -> dict[str, object]:
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


@pytest.fixture
async def role_mutation_case(authorization_factory):
    """Seed one active project manager and one independent target actor."""
    case = RoleMutationCase()
    async with authorization_factory() as session:
        await seed_role_case(session, case)
    return case


async def seed_role_case(session: AsyncSession, case: RoleMutationCase) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            ActorProfile(
                id=str(case.caller_id),
                actor_kind="human",
                status="active",
                provisioning_method="automatic_first_access",
                created_by=str(case.caller_id),
            ),
            ActorIdentityLink(
                id=str(case.caller_link_id),
                actor_profile_id=str(case.caller_id),
                issuer="https://identity.flowresearch.tech",
                subject=f"role-caller-{case.caller_id}",
                subject_kind="human",
                status="active",
                linked_by=str(case.caller_id),
                last_verified_at=now,
            ),
            ActorProfile(
                id=str(case.target_id),
                actor_kind="human",
                status="active",
                provisioning_method="automatic_first_access",
                created_by=str(case.target_id),
            ),
            ActorIdentityLink(
                id=str(case.target_link_id),
                actor_profile_id=str(case.target_id),
                issuer="https://identity.flowresearch.tech",
                subject=f"role-target-{case.target_id}",
                subject_kind="human",
                status="active",
                linked_by=str(case.target_id),
                last_verified_at=now,
            ),
            AdminRoleGrant(
                id=case.bootstrap_grant_id,
                target_actor_profile_id=str(case.caller_id),
                role="access_administrator",
                scope_type="system",
                scope_project_id=None,
                status="active",
                version=1,
                granted_by_actor_profile_id=None,
                granted_by_system_principal="workstream:system:bootstrap",
                granted_by_admin_role_grant_id=None,
                grant_reason="project-role test bootstrap",
            ),
        ]
    )
    await session.flush()
    await session.execute(
        text(
            "update authority_control set bootstrap_completed=true, version=1, "
            "bootstrap_grant_id=:grant_id, updated_at=clock_timestamp() where id=1"
        ),
        {"grant_id": str(case.bootstrap_grant_id)},
    )
    await session.commit()
    await seed_historical_project(
        session,
        project_id=str(case.project_id),
        name="Project-role evidence",
        slug=f"project-role-{case.project_id}",
    )
    await session.commit()
    session.add(
        AdminRoleGrant(
            id=case.manager_grant_id,
            target_actor_profile_id=str(case.caller_id),
            role="project_manager",
            scope_type="project",
            scope_project_id=str(case.project_id),
            status="active",
            version=1,
            granted_by_actor_profile_id=str(case.caller_id),
            granted_by_system_principal=None,
            granted_by_admin_role_grant_id=case.bootstrap_grant_id,
            grant_reason="project-role test manager",
        )
    )
    await session.commit()


@asynccontextmanager
async def mutation_runtime(factory, context: HumanAuthorizationContext):
    async with factory() as session:
        repository = AdminAuthorizationRepository(session)
        authorization = AuthorizationService(session, context, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, context, authorization, repository)
        try:
            yield session, repository, prepared
        finally:
            prepared.close()
