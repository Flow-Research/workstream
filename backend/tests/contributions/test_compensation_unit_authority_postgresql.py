"""Real AUTH/PREP proof that only exact Finance Authority creates a points unit."""

from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from app.adapters.auth import contribution_policy_authorization
from app.adapters.contributions import project_compensation_unit_service
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.contributions.api import (
    ContributionPolicyAuthorizationDenied,
    ContributionPolicyConflict,
    ProjectCompensationUnitCreateRequest,
)
from app.modules.contributions.models import ProjectCompensationUnit
from project_create_fixtures import insert_historical_project
from tests.projects.guide_compilation.proposals.pg_support import (
    revoke_review_grant,
    seed_review_actor,
)

ACTION = "contribution.compensation_unit.create"


@pytest.fixture(name="authority_database_env")
def _authority_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _project() -> UUID:
    project_id = new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        await insert_historical_project(
            session, project_id=str(project_id), name="Points project",
            slug=f"points-{project_id.hex}",
        )
    return project_id


def _context(actor) -> HumanAuthorizationContext:
    return HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id, identity_link_id=actor.identity_link_id,
        actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )


async def _create(
    actor, project_id: UUID, operation_id: UUID | None = None, *, unit_code: str = "FLOW",
    context_actor=None,
):
    request = ProjectCompensationUnitCreateRequest(
        operation_id=operation_id or new_record_id(), actor_profile_id=actor.actor_profile_id,
        project_id=project_id, instrument_type="project_points", unit_code=unit_code,
    )
    context = _context(context_actor or actor)
    async with db_session.get_session_factory()() as session, session.begin():
        return await project_compensation_unit_service(
            session, mutation_authorization=contribution_policy_authorization(session, context),
        ).create(request)


async def _unit_count() -> int:
    async with db_session.get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(ProjectCompensationUnit))


async def _allowed_evidence(actor_id: UUID) -> list[tuple[str, str, str | None]]:
    async with db_session.get_session_factory()() as session:
        rows = await session.execute(text(
            "select event_type, permission_id, project_id::text from audit_events "
            "where action_id=:action and actor_id=:actor order by occurred_at"
        ), {"action": ACTION, "actor": str(actor_id)})
        return [tuple(row) for row in rows]


@pytest.mark.parametrize("scope", ["project", "system"])
@pytest.mark.asyncio
async def test_finance_authority_creates_unit_and_records_allowed_evidence(
    authority_database_env: str, scope: str
) -> None:
    project_id = await _project()
    factory = db_session.get_session_factory()
    finance, _ = await seed_review_actor(
        factory, project_id, role="finance_authority", scope=scope
    )

    result = await _create(finance, project_id)

    assert result.actor_profile_id == finance.actor_profile_id and result.unit_code == "FLOW"
    evidence = await _allowed_evidence(finance.actor_profile_id)
    assert evidence and {row[0] for row in evidence} == {"SensitiveAuthorizationAllowed"}
    assert {row[1] for row in evidence} == {"compensation.policy.manage"}
    assert {row[2] for row in evidence} == {str(project_id)}


@pytest.mark.parametrize(
    ("role", "scope", "target"),
    [
        ("project_manager", "project", "same"),
        ("project_manager", "system", "same"),
        ("operator", "system", "same"),
        ("finance_authority", "project", "other"),
    ],
)
@pytest.mark.asyncio
async def test_other_roles_and_foreign_scopes_are_denied_without_effects(
    authority_database_env: str, role: str, scope: str, target: str
) -> None:
    project_id, other_project = await _project(), await _project()
    factory = db_session.get_session_factory()
    actor, _ = await seed_review_actor(
        factory, other_project if target == "other" else project_id, role=role, scope=scope
    )

    with pytest.raises(ContributionPolicyAuthorizationDenied) as denied:
        await _create(actor, project_id)
    assert str(denied.value) == "contribution_policy_unavailable"
    assert await _unit_count() == 0


@pytest.mark.asyncio
async def test_missing_and_foreign_projects_produce_the_same_concealed_denial(
    authority_database_env: str,
) -> None:
    own_project, foreign_project = await _project(), await _project()
    factory = db_session.get_session_factory()
    finance, _ = await seed_review_actor(factory, own_project, role="finance_authority")

    outcomes = []
    for project_id in (foreign_project, new_record_id()):
        with pytest.raises(ContributionPolicyAuthorizationDenied) as denied:
            await _create(finance, project_id)
        outcomes.append((type(denied.value), str(denied.value)))
    assert outcomes[0] == outcomes[1]
    assert await _unit_count() == 0


@pytest.mark.asyncio
async def test_replay_requires_current_finance_authority(authority_database_env: str) -> None:
    project_id = await _project()
    factory = db_session.get_session_factory()
    finance, grant = await seed_review_actor(factory, project_id, role="finance_authority")
    operation_id = new_record_id()
    first = await _create(finance, project_id, operation_id)
    assert await _create(finance, project_id, operation_id) == first

    await revoke_review_grant(factory, finance, grant)

    with pytest.raises(ContributionPolicyAuthorizationDenied):
        await _create(finance, project_id, operation_id)
    assert await _unit_count() == 1


@pytest.mark.asyncio
async def test_non_finance_reuse_of_a_known_operation_is_denied_not_disclosed(
    authority_database_env: str,
) -> None:
    project_id = await _project()
    factory = db_session.get_session_factory()
    finance, _ = await seed_review_actor(factory, project_id, role="finance_authority")
    manager, _ = await seed_review_actor(factory, project_id, role="project_manager")
    operation_id = new_record_id()
    await _create(finance, project_id, operation_id)

    for unit_code in ("FLOW", "OTHER"):
        with pytest.raises(ContributionPolicyAuthorizationDenied):
            await _create(manager, project_id, operation_id, unit_code=unit_code)
    assert await _unit_count() == 1


@pytest.mark.asyncio
async def test_request_actor_must_be_the_authenticated_actor(authority_database_env: str) -> None:
    project_id = await _project()
    factory = db_session.get_session_factory()
    finance, _ = await seed_review_actor(factory, project_id, role="finance_authority")
    other, _ = await seed_review_actor(factory, project_id, role="finance_authority")

    with pytest.raises(ContributionPolicyAuthorizationDenied):
        await _create(other, project_id, context_actor=finance)
    assert await _unit_count() == 0


@pytest.mark.asyncio
async def test_system_finance_learns_only_not_found_for_a_missing_project(
    authority_database_env: str,
) -> None:
    factory = db_session.get_session_factory()
    finance, _ = await seed_review_actor(factory, None, role="finance_authority", scope="system")

    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_not_found"):
        await _create(finance, new_record_id())
    assert await _unit_count() == 0
